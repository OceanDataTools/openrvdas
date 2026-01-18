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

            fields (dict): Mapping of field names to target types (e.g., {'temp': 'float'}).
                           If provided, ConvertFieldsTransform is instantiated internally.

            lat_lon_fields (dict): Mapping for NMEA lat/lon conversion.

            delete_source_fields (bool): Remove original fields after conversion.

            delete_unconverted_fields (bool): Remove fields that were not converted.
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        # 1. Initialize the Parser (RegexParser)
        self.parser = regex_parser.RegexParser(
            record_format=record_format,
            field_patterns=field_patterns,
            data_id=data_id,
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

    def transform(self, record: str) -> Union[DASRecord, List[DASRecord], None]:
        """
        Parse the record, optionally convert fields, and return the result.
        """
        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # BaseModule
            return self.digest_record(record)  # BaseModule

        # 1. Parse
        # Returns a DASRecord
        parsed_record = self.parser.parse_record(record)

        if not parsed_record:
            return None

        # 2. Convert Fields
        if self.converter:
            # ConvertFieldsTransform modifies in place or returns a copy
            # It expects DASRecord (or list) and returns DASRecord (or list)
            parsed_record = self.converter.transform(parsed_record)
            if not parsed_record:
                return None

        return parsed_record


# Alias for backward compatibility
RegexTransform = RegexParseTransform
