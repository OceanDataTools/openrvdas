#!/usr/bin/env python3

import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import record_parser  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402

################################################################################
class ParseTransform(Transform):
    """Parse a "<data_id> <timestamp> <message>" record and return
    corresponding dict of values (or JSON or DASRecord if specified)."""

    def __init__(self, record_format=None, field_patterns=None, metadata=None,
                 definition_path=record_parser.DEFAULT_DEFINITION_PATH,
                 return_json=False, return_das_record=False,
                 metadata_interval=None, strip_unprintable=False, quiet=False,
                 prepend_data_id=False, delimiter=':'):
        """
        ```
        record_format
                If not None, a custom record format to use for parsing records.
                The default, defined in logger/utils/record_parser.py, is
                '{data_id:w} {timestamp:ti} {field_string}'.

        field_patterns
                If not None, a list of parse patterns to be tried instead
                of looking for device definitions along the definition path.

        metadata
                If field_patterns is not None, the metadata to send along with
                data records.

        definition_path
                Wildcarded path matching YAML definitions for devices. Used
                only if 'field_patterns' is None

        return_json
                Return a JSON-encoded representation of the dict
                instead of a dict itself.

        return_das_record
                Return a DASRecord object.

        metadata_interval
                If not None, include the description, units and other metadata
                pertaining to each field in the returned record if those data
                haven't been returned in the last metadata_interval seconds.

        strip_unprintable
                Strip out and ignore any leading or trailing non-printable binary
                characters in the string to be parsed.

        quiet - if not False, don't complain when unable to parse a record.

        prepend_data_id
                If true prepend the instrument data_id to field_names in the record.

        delimiter
                The string to insert between data_id and field_name when prepend_data_id is true.
                Defaults to ':'.
                Not used if prepend_data_id is false.

        ```
        """
        self.parser = record_parser.RecordParser(
            record_format=record_format,
            field_patterns=field_patterns,
            metadata=metadata,
            definition_path=definition_path,
            return_json=return_json,
            return_das_record=return_das_record,
            metadata_interval=metadata_interval,
            strip_unprintable=strip_unprintable,
            quiet=quiet,
            prepend_data_id=prepend_data_id,
            delimiter=delimiter)

    ############################
    def transform(self, record):
        """Parse record and return DASRecord."""
        if record is None:
            return None

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list.
        if type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record))
            return results

        return self.parser.parse_record(record)
