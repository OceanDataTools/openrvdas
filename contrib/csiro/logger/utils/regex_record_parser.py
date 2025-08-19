#!/usr/bin/env python3

"""
Organisation: CSIRO

Tools for parsing NMEA and other text records using regular expressions.

By default, will load device and device_type definitions from files in
contrib/devices/*.yaml. Please see documentation in
contrib/devices/README.md for a description of the format these
definitions should take.
"""
import datetime
import glob
import json
import logging
import parse
import pprint
import re
import sys
import struct

# Append openrvdas root to syspath prior to importing openrvdas modules
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import read_config  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402

# Dict of format types that extend the default formats recognized by the
# parse module.
# from logger.utils.record_parser_formats import extra_format_types  # noqa: E402
from logger.utils.record_parser import RecordParser

DEFAULT_DEFINITION_PATH = 'contrib/devices/*.yaml'
DEFAULT_RECORD_FORMAT = '{data_id:w} {timestamp:ti} {field_string}'


def hexadecimal(value):
    return bytearray.fromhex(value)

def hex_int(value):
    return struct.unpack('!H', bytearray.fromhex(value))[0]

# Note: untested, must be 4 bytes
def hex_float(value):
    return struct.unpack('!f', bytearray.fromhex(value))[0]

# Note: untested, must be 8 bytes
def hex_double(value):
    return struct.unpack('!d', bytearray.fromhex(value))[0]


# these formats are in addition to standard python data types
extra_data_formats = {
    'hexadecimal': hexadecimal,
    'hex_float': hex_float,
    'hex_double': hex_double
}


class RegexRecordParser(RecordParser):
    ############################
    def __init__(self, record_format=None,
                 field_patterns=None, metadata=None,
                 definition_path=DEFAULT_DEFINITION_PATH,
                 return_das_record=False, return_json=False,
                 metadata_interval=None, quiet=False,
                 prepend_data_id=False, delimiter=':'):
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
        super().__init__(record_format=record_format,
                         field_patterns=field_patterns, metadata=metadata,
                         definition_path=definition_path,
                         return_das_record=return_das_record, return_json=return_json,
                         metadata_interval=metadata_interval, quiet=quiet,
                         prepend_data_id=prepend_data_id, delimiter=delimiter)

        self.data_type_map = {}
        # Build dict that maps data formats
        for instrument, definition in self.device_types.items():
            self.data_type_map[instrument] = {}
            for field_name, field_info in definition['fields'].items():
                if 'data_type' in field_info:
                    self.data_type_map[instrument][field_name] = field_info['data_type']
                # If no data type is provided then the default is string
                else:
                    self.data_type_map[instrument][field_name] = 'str'

    ############################
    def parse_record(self, record):
        # Do the usual record parser stuff before adding on the data type mapping
        parsed_record = RecordParser.parse_record(self, record)

        if parsed_record:
            # Check that there are fields to cenvert
            if parsed_record['fields']:
                pass
            else:
                logging.debug("Fields are empty, so return None")
                return None

            # Find the device name from the data id (e.g. investigator_sstrm -> ISAR-5D)
            device_type = self.devices[parsed_record["data_id"]]['device_type']

            for key, value in parsed_record['fields'].items():
                # Find the original key from the value in self.devices (e.g. Pressure: 'PressureValue', 'PressureValue' -> 'Pressure')
                fields = self.devices[parsed_record["data_id"]]['fields']
                value_index = list(fields.values()).index(key)
                devices_key = list(fields.keys())[value_index]

                # ----- SPECIAL CONVERSIONS ------
                if self.data_type_map[device_type][devices_key] in extra_data_formats:
                    try:
                        op = extra_data_formats.get(self.data_type_map[device_type][devices_key])
                        parsed_record['fields'][key] = op(value)
                    except Exception as e:
                        logging.warning('Unable convert to extra data type "%s" with exception %s',
                                        self.data_type_map[device_type][devices_key], e)
                # ----- STANDARD PYTHON DATA TYPE CONVERSIONS ------
                # Need this if statement because eval can do some funky stuff when casting a string of numbers to a string
                # (e.g. eval(str, '10/20') -> '0.5')
                elif self.data_type_map[device_type][devices_key] != 'str':
                    try:
                        parsed_record['fields'][key] = eval(self.data_type_map[device_type][devices_key] + '("' + value + '")')
                    except Exception as e:
                        if value == '' or value == '-':
                            parsed_record['fields'][key] = None
                            logging.debug('Could not convert string "%s" to "%s" for field "%s" in record "%s", '
                                            'inserting "None" instead', value, self.data_type_map[device_type][devices_key], key, record)
                        else:
                            logging.warning(
                                'Unable convert to data type "%s" for the field "%s" with call eval("%s(%s)") with exception %s, '
                                'consider adding a new extra_data_format',
                                self.data_type_map[device_type][devices_key], key, self.data_type_map[device_type][devices_key], value, e)

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

        # DPC had updated this code block upstream, it was not correctly handling
        # dicts in the older version.
        elif isinstance(compiled_field_patterns, dict):
            for message_type, pattern in compiled_field_patterns.items():
                fields, int_message_type = self._parse_field_string(field_string, pattern)
                message_type = int_message_type or message_type
                if fields is not None:
                    break
        else:
            raise ValueError('Unexpected pattern type in parser: %s'
                             % type(compiled_field_patterns))

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
            raise ValueError('Passed field_patterns must be str, list or dict. Found %s: %s'
                             % (type(field_patterns), str(field_patterns)))
