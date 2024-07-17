#!/usr/bin/env python3

"""Tools for parsing NMEA and other text records using regular expressions.

By default, will load device and device_type definitions from files in
local/devices/*.yaml. Please see documentation in
local/devices/README.md for a description of the format these
definitions should take.
"""

import logging
import re
import sys

# Append openrvdas root to syspath prior to importing openrvdas modules
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import read_config  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.utils.record_parser import RecordParser


DEFAULT_DEFINITION_PATH = "local/devices/*.yaml"
DEFAULT_RECORD_FORMAT = "{data_id:w} {timestamp:ti} {field_string}"


class RegexRecordParser(RecordParser):
    ############################
    def __init__(
        self,
        record_format=None,
        field_patterns=None,
        metadata=None,
        definition_path=DEFAULT_DEFINITION_PATH,
        return_das_record=False,
        return_json=False,
        metadata_interval=None,
        quiet=False,
        prepend_data_id=False,
        delimiter=":",
    ):
        """Create a parser that will parse field values out of a text record
        and return either a Python dict of data_id, timestamp and fields,
        a JSON encoding of that dict, or a binary DASRecord.
        ```
        record_format - string for parse.parse() to use to break out data_id
            and timestamp from the rest of the message. By default this will
            look for 'data_id timestamp field_string', where 'field_string'
            is a str containing the fields to be parsed.

        field_patterns
            If not None, a list of regular expression patterns to be tried instead
            of looking for device definitions along the definition path,
            or a dict of message_type:[parse_pattern, parse_pattern].

        metadata
            If field_patterns is not None, the metadata to send along with
            data records.

        definition_path - a comma-separated set of file globs in which to look
            for device and device_type definitions with which to parse message.

        return_json - return the parsed fields as a JSON encoded dict

        return_das_record - return the parsed fields as a DASRecord object

        metadata_interval - if not None, include the description, units
            and other metadata pertaining to each field in the returned
            record if those data haven't been returned in the last
            metadata_interval seconds.

        quiet - if not False, don't complain when unable to parse a record.

        prepend_data_id - If true prepend the instrument data_id to field_names
            in the record.

        delimiter
            The string to insert between data_id and field_name when prepend_data_id is true.
            Defaults to ':'.
            Not used if prepend_data_id is false.
        ```
        """
        super().__init__(
            record_format=record_format,
            field_patterns=field_patterns,
            metadata=metadata,
            definition_path=definition_path,
            return_das_record=return_das_record,
            return_json=return_json,
            metadata_interval=metadata_interval,
            quiet=quiet,
            prepend_data_id=prepend_data_id,
            delimiter=delimiter,
        )

        self.data_type_map = {}
        # Build dict that maps data formats
        for instrument, definition in self.device_types.items():
            self.data_type_map[instrument] = {}
            for field_name, field_info in definition["fields"].items():
                if "data_type" in field_info:
                    self.data_type_map[instrument][field_name] = field_info["data_type"]
                # If no data type is provided then the default is string
                else:
                    self.data_type_map[instrument][field_name] = "str"

    ############################
    def parse_record(self, record):
        # Do the usual record parser stuff before adding on the data type mapping
        parsed_record = RecordParser.parse_record(self, record)

        if parsed_record:
            # Check that there are fields to cenvert
            if parsed_record["fields"]:
                pass
            else:
                logging.debug("Fields are empty, so return None")
                return None

        return parsed_record

    def _parse_field_string(self, field_string, compiled_field_patterns):
        # Default if we don't match anything
        fields = None
        message_type = None

        # If our pattern(s) are just a single compiled parser, try parsing and
        # return with no message type.
        if isinstance(compiled_field_patterns, re.Pattern):
            result = compiled_field_patterns.match(field_string)
            if result:
                fields = result.groupdict()

        # Else, if it's a list, try it out on all the elements.
        elif isinstance(compiled_field_patterns, list):
            for pattern in compiled_field_patterns:
                if isinstance(pattern, re.Pattern):
                    result = pattern.match(field_string)
                    if result:
                        fields = result.groupdict()
                        message_type = message_type
                        break

        # If it's a dict, try out on all values, using the key as message type.
        # It's syntactically possible for the internal set of patterns to have
        # their own message types. Not sure why someone would ever create patterns
        # that did this, but if they do, let that override our base one.
        elif isinstance(compiled_field_patterns, dict):
            for message_type, patterns in compiled_field_patterns.items():
                for pattern in patterns:
                    if isinstance(pattern, re.Pattern):
                        result = pattern.match(field_string)
                        if result:
                            fields = result.groupdict()
                            message_type = message_type
                            break
                if result:
                    break
        else:
            raise ValueError(
                "Unexpected pattern type in parser: %s" % type(compiled_field_patterns)
            )

        return fields, message_type

    ############################
    def _compile_formats_from_patterns(self, field_patterns):
        """Return a list/dict of patterns compiled from the
        str/list/dict of passed field_patterns.
        """
        if isinstance(field_patterns, str):
            return [re.compile(field_patterns)]
        elif isinstance(field_patterns, list):
            return [re.compile(p) for p in field_patterns]
        elif isinstance(field_patterns, dict):
            compiled_field_patterns = {}
            for message_type, message_pattern in field_patterns.items():
                compiled_patterns = self._compile_formats_from_patterns(message_pattern)
                compiled_field_patterns[message_type] = compiled_patterns
            return compiled_field_patterns

        else:
            raise ValueError(
                "Passed field_patterns must be str, list or dict. Found %s: %s"
                % (type(field_patterns), str(field_patterns))
            )
