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
                 fields: Dict = None,
                 delete_source_fields: bool = False,
                 delete_unconverted_fields: bool = False,
                 metadata: Dict = None,
                 metadata_interval: float = None,
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

            delete_source_fields (bool): Remove original fields after conversion.

            delete_unconverted_fields (bool): Remove fields that were not converted.

            metadata (dict): If field_patterns is not None, the metadata to send along with
                             data records.

            metadata_interval (float): If not None, include the description, units and
                                       other metadata pertaining to each field in the
                                       returned record if those data haven't been returned
                                       in the last metadata_interval seconds.
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        # Check for conflict
        if field_patterns and definition_path:
            raise ValueError('RegexParseTransform: Both field_patterns and definition_path '
                             'specified. Please specify only one.')

        self.devices = {}
        self.device_types = {}
        self.type_converters = {}

        self.metadata = metadata or {}
        self.metadata_interval = metadata_interval
        self.metadata_last_sent = {}

        # If field patterns not provided, look them up in definitions
        if field_patterns is None:
            definition_path = definition_path or DEFAULT_DEFINITION_PATH
            # Load definitions populate self.devices and self.device_types
            # And returns the aggregated patterns for the parser
            field_patterns = self._load_definitions(definition_path)

            # If metadata not explicitly provided, try to compile it from definitions
            if not self.metadata and self.metadata_interval:
                self._compile_metadata()

        # 1. Initialize the Parser (RegexParser)
        # We pass the aggregated patterns. RegexParser extracts fields based on regex names.
        self.parser = regex_parser.RegexParser(
            record_format=record_format,
            field_patterns=field_patterns,
            data_id=data_id,
            quiet=self.quiet
        )

        # 3. Converter for generic fields (passed in args)
        self.converter = None
        if fields and ConvertFieldsTransform:
            self.converter = ConvertFieldsTransform(
                fields=fields,
                delete_source_fields=delete_source_fields,
                delete_unconverted_fields=delete_unconverted_fields,
                quiet=self.quiet
            )

    def _load_definitions(self, definition_path):
        """Load device definitions and return aggregated field patterns.
        Populates self.devices and self.device_types.
        """
        field_patterns = {}

        if not definition_path:
            return field_patterns

        def_files = []
        for path_glob in definition_path.split(','):
            def_files.extend(glob.glob(path_glob.strip()))

        if not def_files:
            return field_patterns

        for filename in def_files:
            # read_config handles includes recursively? No, we must call it.
            new_defs = read_config.read_config(filename)
            new_defs = read_config.expand_includes(new_defs)

            # Store device_types
            if 'device_types' in new_defs:
                for dt_name, dt_def in new_defs['device_types'].items():
                    self.device_types[dt_name] = dt_def
                    # Aggregate formats (regexes)
                    dt_formats = dt_def.get('format', {})
                    if isinstance(dt_formats, dict):
                        field_patterns.update(dt_formats)

                    # Create cached component converter for this type
                    # CSIRO format: fields: {name: {data_type: type}}
                    # ConvertFieldsTransform format: {name: {data_type: type}} or {name: type}
                    # It matches perfectly.
                    dt_fields = dt_def.get('fields', {})
                    if dt_fields and ConvertFieldsTransform:
                        self.type_converters[dt_name] = ConvertFieldsTransform(
                            fields=dt_fields,
                            quiet=self.quiet
                        )

            # Store devices
            if 'devices' in new_defs:
                for d_name, d_def in new_defs['devices'].items():
                    self.devices[d_name] = d_def

        return field_patterns

    def _compile_metadata(self):
        """
        Compile metadata from device definitions if available.
        Logic adapted from RecordParser.
        """
        # It's a map from variable name to the device and device type it
        # came from, along with device type variable and its units and
        # description, if provided in the device type definition.
        for device, device_def in self.devices.items():
            device_type_name = device_def.get('device_type')
            if not device_type_name:
                continue

            device_type_def = self.device_types.get(device_type_name)
            if not device_type_def:
                continue

            device_type_fields = device_type_def.get('fields')
            if not device_type_fields:
                continue

            fields = device_def.get('fields')
            if not fields:
                continue

            # e.g. device_type_field = GPSTime, device_field = S330GPSTime
            for device_type_field, device_field in fields.items():
                # e.g. GPSTime: {'units':..., 'description':...}
                field_desc = device_type_fields.get(device_type_field)

                # field_desc might be a string (type) or dict (metadata) or None
                if not field_desc or not isinstance(field_desc, dict):
                    continue

                self.metadata[device_field] = {
                    'device': device,
                    'device_type': device_type_name,
                    'device_type_field': device_type_field,
                }
                # Copy relevant keys like units, description
                for k in ['units', 'description']:
                    if k in field_desc:
                        self.metadata[device_field][k] = field_desc[k]

    def transform(self, record: str) -> Union[DASRecord, List[DASRecord], None]:
        """
        Parse the record, optionally convert fields, and return the result.
        """
        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # BaseModule
            return self.digest_record(record)  # BaseModule

        # 1. Parse (Regex)
        parsed_record = self.parser.parse_record(record)

        if not parsed_record:
            return None

        # 2. Device-Specific Logic
        # Try to match data_id to a known device
        data_id = parsed_record.data_id
        if data_id in self.devices:
            device_def = self.devices[data_id]
            device_type = device_def.get('device_type')

            # A. Type Conversion (delegated to cached ConvertFieldsTransform)
            if device_type in self.type_converters:
                converter = self.type_converters[device_type]
                parsed_record = converter.transform(parsed_record)
                if not parsed_record:
                    return None

            # B. Field Renaming / Filtering
            # Only retain fields that are in the device's 'fields' map
            device_fields_map = device_def.get('fields', {})
            if device_fields_map:
                new_fields = {}
                for original_name, mapped_name in device_fields_map.items():
                    if original_name in parsed_record.fields:
                        # Use the mapped name (value)
                        new_fields[mapped_name] = parsed_record.fields[original_name]

                parsed_record.fields = new_fields

        # 3. Generic Converter (ConvertFieldsTransform)
        # Apply this AFTER device logic if configured (e.g. explicit 'fields' arg)
        if self.converter:
            parsed_record = self.converter.transform(parsed_record)
            if not parsed_record:
                return None

        # 4. Metadata Injection
        # If we have parsed fields, see if we also have metadata. Are we
        # supposed to occasionally send it for our variables? Is it time
        # to send it again?
        if self.metadata and self.metadata_interval:
            metadata_fields = {}
            timestamp = parsed_record.timestamp or 0

            for field_name in parsed_record.fields:
                last_metadata_sent = self.metadata_last_sent.get(field_name, 0)
                time_since_send = timestamp - last_metadata_sent

                # Check if it's time to send
                if time_since_send > self.metadata_interval:
                    field_metadata = self.metadata.get(field_name)
                    if field_metadata:
                        metadata_fields[field_name] = field_metadata
                        self.metadata_last_sent[field_name] = timestamp

            # If we collected any metadata to send, attach it
            if metadata_fields:
                if parsed_record.metadata is None:
                    parsed_record.metadata = {}
                parsed_record.metadata['fields'] = metadata_fields

        return parsed_record


# Alias for backward compatibility
RegexTransform = RegexParseTransform
