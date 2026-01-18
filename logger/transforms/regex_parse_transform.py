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
import glob
from typing import Union, Dict, List

# Adjust paths as per your project structure
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402
from logger.transforms.convert_fields_transform import ConvertFieldsTransform  # noqa: E402

# Uses the 're' based parser (formerly used by RegexTransform)
from logger.utils import regex_parser  # noqa: E402
from logger.utils import read_config  # noqa: E402

DEFAULT_DEFINITION_PATH = 'contrib/devices/*.yaml'


class RegexParseTransform(Transform):
    r"""
    Parses a string record into a DASRecord using regular expressions,
    with optional field type conversion.

    This implementation uses the 're' module for parsing (via regex_parser)
    and does NOT depend on ParseTransform.

    **Example Configuration:**

    .. code-block:: yaml

        - class: RegexParseTransform
          module: logger.transforms.regex_parse_transform
          kwargs:
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
                 definition_path: str = None,

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

            definition_path (str): Wildcarded path matching YAML definitions for devices.
                                   Used only if 'field_patterns' is None.
                                   Defaults to 'contrib/devices/*.yaml'.

            fields (dict): Mapping of field names to target types (e.g., {'temp': 'float'}).
                           If provided, ConvertFieldsTransform is instantiated internally.

            lat_lon_fields (dict): Mapping for NMEA lat/lon conversion.

            delete_source_fields (bool): Remove original fields after conversion.

            delete_unconverted_fields (bool): Remove fields that were not converted.
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        # Check for conflict
        if field_patterns and definition_path:
            raise ValueError('RegexParseTransform: Both field_patterns and definition_path '
                             'specified. Please specify only one.')

        # If field patterns not provided, look them up in definitions
        if field_patterns is None:
            definition_path = definition_path or DEFAULT_DEFINITION_PATH
            field_patterns, loaded_fields = self._load_definitions(definition_path)
            # Merge loaded fields (types) with passed fields argument
            if loaded_fields:
                if fields is None:
                    fields = {}
                loaded_fields.update(fields)
                fields = loaded_fields

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

    def _load_definitions(self, definition_path):
        """Load device definitions from YAML files and extract regex patterns and field types.
        """
        field_patterns = {}
        fields = {}

        if not definition_path:
            return field_patterns, fields

        # We can implement a simplified version of RecordParser._read_definitions
        # tailored to what we need (regexes and types)
        def_files = []
        for path_glob in definition_path.split(','):
            def_files.extend(glob.glob(path_glob.strip()))

        if not def_files:
            return field_patterns, fields

        for filename in def_files:
            new_defs = read_config.read_config(filename)
            # We are interested mainly in 'device_types'
            # (which contain 'format' and 'fields')
            if 'device_types' in new_defs:
                for dt_name, dt_def in new_defs['device_types'].items():
                    # Extract formats (regexes)
                    # format is typically dict {MsgType: regex}
                    dt_formats = dt_def.get('format', {})
                    if isinstance(dt_formats, dict):
                        field_patterns.update(dt_formats)

                    # Extract field types
                    dt_fields = dt_def.get('fields', {})
                    for field_name, field_def in dt_fields.items():
                        # field_def might be a dict with 'data_type'
                        if isinstance(field_def, dict):
                            dtype = field_def.get('data_type')
                            if dtype:
                                fields[field_name] = dtype

        return field_patterns, fields

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
