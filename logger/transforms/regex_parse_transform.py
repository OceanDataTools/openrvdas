#!/usr/bin/env python3
"""
Unified RegexParseTransform.

This class unifies the functionality of the CORIOLIX RegexTransform and
CSIRO's RegexParseTransform into a single, robust regex-based transformer.

It uses the pure-regex parsing engine (logger.utils.regex_parser) rather than
the format-string parser, and allows for optional type conversion of fields.

It also allows use of dicts of {message_type: regex} in field_patterns to capture
message_type, and allows specifying a data_id, either if the data string doesn't
have one, or to override the one that is there.
"""

import sys
import json
from typing import Union, Dict, List

# Adjust paths as per your project structure
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402
from logger.transforms.convert_fields_transform import ConvertFieldsTransform  # noqa: E402

# Uses the 're' based parser (formerly used by RegexTransform)
from logger.utils import regex_parser  # noqa: E402


class RegexParseTransform(Transform):
    r"""
    Parses a string record into a Python dict (or DASRecord/JSON) using
    regular expressions, with optional field type conversion.

    This implementation uses the 're' module for parsing (via regex_parser)
    and does NOT depend on ParseTransform.

    **Example Configuration:**

    .. code-block:: yaml

        - class: RegexParseTransform
          module: logger.transforms.regex_parse_transform
          kwargs:
            return_das_record: true
            data_id: gnsspo112593  # Overrides or fills in data_id
            field_patterns:
              GPZDA: '^\WGPZDA,(?P<utc_time>\d+\.\d+),(?P<day>\d{2}),(?P<month>\d{2}),
                      (?P<year>\d{4}),(?P<tzoffset_hours>\d{0,2}),
                      (?P<tzoffset_mins>\d{0,2})\*(?P<checksum>[0-9A-F]{2})$'
              GPGGA: '^\WGPGGA,(?P<utc_position_fix>\d+\.\d+),(?P<latitude>\d+\.\d+),
                      (?P<latitude_dir>[NS]),(?P<longitude>\d+\.\d+),(?P<longitude_dir>[EW]),
                      (?P<gps_quality_indicator>\d+),(?P<num_sat_vis>\d+),(?P<hdop>\d+\.\d+),
                      (?P<ortho_height>\-?\d+\.\d+),M,(?P<geoid_separation>\-?\d+\.\d+),M,
                      (?P<age>[\d\.]*)?,(\d{4})?\*(?P<checksum>[0-9A-F]{2})$'

            # --- Field Conversion Arguments ---
            delete_source_fields: true
            delete_unconverted_fields: true
            fields:
              latitude:
                data_type: float
              cog_true:
                data_type: float
            lat_lon_fields:
              latitude: [latitude, latitude_dir]
              longitude: [longitude, longitude_dir]
    """

    def __init__(self,
                 # --- Parsing Arguments (RegexParser) ---
                 record_format: str = None,
                 field_patterns: Union[List, Dict] = None,
                 data_id: str = None,

                 # --- Output Format Arguments ---
                 return_json: bool = False,
                 return_das_record: bool = False,

                 # --- Type Conversion Arguments (ConvertFieldsTransform) ---
                 fields: Dict = None,
                 lat_lon_fields: Dict = None,
                 delete_source_fields: bool = False,
                 delete_unconverted_fields: bool = False,
                 **kwargs):
        """
        Args:
            record_format (str): A regex string to match the record envelope (timestamp, data_id).
                                 Defaults to regex_parser.DEFAULT_RECORD_FORMAT.

            field_patterns (list/dict):
                - A list of regex patterns to match the field body.
                - A dict of {message_type: pattern}.

            data_id (str): If specified, this string is used as the data_id for all records,
                           overriding any data_id extracted from the source record.

            return_json (bool): Return a JSON string representation of the record.

            return_das_record (bool): Return a DASRecord object (default is dict).

            fields (dict): Mapping of field names to target types (e.g., {'temp': 'float'}).
                           If provided, ConvertFieldsTransform is instantiated internally.

            lat_lon_fields (dict): Mapping for NMEA lat/lon conversion.

            delete_source_fields (bool): Remove original fields after conversion.

            delete_unconverted_fields (bool): Remove fields that were not converted.
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        self.return_json = return_json
        self.return_das_record = return_das_record
        # self.quiet = quiet  # is taken care of in BaseModule init from **kwargs

        # 1. Initialize the Parser (RegexParser)
        # We configure it to return a dict or DASRecord initially so we can process
        # fields. We handle the final JSON serialization ourselves if requested.
        use_das_record = True if (return_das_record or fields or lat_lon_fields) else False

        self.parser = regex_parser.RegexParser(
            record_format=record_format,
            field_patterns=field_patterns,
            data_id=data_id,
            return_json=False,  # Handle JSON manually after conversion
            return_das_record=use_das_record,
            quiet=self.quiet
        )

        # 2. Initialize the Converter (if requested)
        self.converter = None
        if (fields or lat_lon_fields) and ConvertFieldsTransform:
            self.converter = ConvertFieldsTransform(
                fields=fields,
                lat_lon_fields=lat_lon_fields,
                delete_source_fields=delete_source_fields,
                delete_unconverted_fields=delete_unconverted_fields,
                quiet=self.quiet
            )

    def transform(self, record: str) -> Union[Dict, str, DASRecord, List]:
        """
        Parse the record, optionally convert fields, and return the result.
        """
        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # BaseModule
            return self.digest_record(record)  # BaseModule

        # 1. Parse
        # Returns a DASRecord (if we asked for it) or a dict
        parsed_record = self.parser.parse_record(record)

        if not parsed_record:
            return None

        # 2. Convert Fields
        if self.converter:
            # ConvertFieldsTransform modifies in place or returns a copy
            parsed_record = self.converter.transform(parsed_record)
            if not parsed_record:
                return None

        # 3. Format Output
        # At this point 'parsed_record' is likely a DASRecord (if we used converter)
        # or a dict (if we didn't use converter and didn't ask for DASRecord).

        if self.return_json:
            if isinstance(parsed_record, DASRecord):
                # Construct dict for serialization
                rec_dict = {
                    'data_id': parsed_record.data_id,
                    'timestamp': parsed_record.timestamp,
                    'fields': parsed_record.fields
                }
                if parsed_record.metadata:
                    rec_dict['metadata'] = parsed_record.metadata
                return json.dumps(rec_dict)
            else:
                return json.dumps(parsed_record)

        elif self.return_das_record:
            # User specifically asked for DASRecord
            if isinstance(parsed_record, dict):
                # Upgrade dict to DASRecord if parser returned dict
                return DASRecord(
                    data_id=parsed_record.get('data_id'),
                    timestamp=parsed_record.get('timestamp'),
                    fields=parsed_record.get('fields'),
                    metadata=parsed_record.get('metadata')
                )
            return parsed_record

        else:
            # User wants a plain dictionary
            if isinstance(parsed_record, DASRecord):
                rec_dict = {
                    'data_id': parsed_record.data_id,
                    'timestamp': parsed_record.timestamp,
                    'fields': parsed_record.fields
                }
                if parsed_record.metadata:
                    rec_dict['metadata'] = parsed_record.metadata
                return rec_dict
            return parsed_record


# Alias for backward compatibility
RegexTransform = RegexParseTransform
