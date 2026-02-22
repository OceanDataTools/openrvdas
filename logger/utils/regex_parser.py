#!/usr/bin/env python3

"""Tools for parsing NMEA and other text records using regex.
"""
import datetime
import logging
import re
import pprint
import sys
import time

from os.path import dirname, realpath


# Append openrvdas root to syspath prior to importing openrvdas modules
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord  # noqa: E402
from logger.utils.read_config import load_definitions  # noqa: E402
from logger.utils.das_record import collect_metadata_for_fields  # noqa: E402

# Import ConvertFieldsTransform, but handle gracefully if unavailable
try:
    from logger.transforms.convert_fields_transform import ConvertFieldsTransform
except ImportError:
    ConvertFieldsTransform = None

# Note: this is a "permissive" regex. It looks for data_id and timestamp prior to field_string,
# But still parses field_string if they are absent
# Works for both "data_id timestamp fields" but also parses "fields" if
# data_id or timestamp are missing

DEFAULT_RECORD_FORMAT = r"^(?:(?P<data_id>\w+)\s+(?P<timestamp>[0-9TZ:\-\.]*)\s+)?(?P<field_string>(.|\r|\n)*)"  # noqa: E501

DEFAULT_DEFINITION_PATH = 'local/devices/*.yaml,contrib/devices/*.yaml'


################################################################################
class RegexParser:
    ############################
    def __init__(self,
                 record_format=None,
                 field_patterns=None,
                 data_id=None,
                 definition_path=None,
                 metadata=None,
                 metadata_interval=None,
                 quiet=False):
        r"""Create a parser that will parse field values out of a text record
        and return a DASRecord object.
        ```
        record_format - string for re.match() to use to break out data_id
            and timestamp from the rest of the message. By default this will
            look for 'data_id timestamp field_string', where 'field_string'
            is a str containing the fields to be parsed.

        field_patterns
            If not None, either
            - a list of regex patterns to be tried
            - a dict of message_type:regex patterns to be tried. When one
              matches, the record's message_type is set accordingly.
            If None and definition_path is provided, patterns are loaded from
            device definition files.

        data_id
            If specified, this string is used as the data_id for all records,
            overriding any data_id extracted from the source record.

        definition_path
            Wildcarded path matching YAML definitions for devices. Used only
            if 'field_patterns' is None. Defaults to DEFAULT_DEFINITION_PATH.
            Comma-separated globs are supported.

        metadata
            If provided, a dict mapping field names to their metadata dicts.
            If None and definition_path is used, metadata is compiled from
            device definitions.

        metadata_interval
            If not None, include the description, units and other metadata
            pertaining to each field in the returned record if those data
            haven't been returned in the last metadata_interval seconds.

        quiet - if not False, don't complain when unable to parse a record.
        ```
        """
        self.quiet = quiet
        self.record_format = record_format or DEFAULT_RECORD_FORMAT
        self.compiled_record_format = re.compile(self.record_format)
        self.data_id = data_id  # Store the data_id override

        # Check for conflict
        if field_patterns and definition_path:
            raise ValueError('RegexParser: Both field_patterns and definition_path '
                             'specified. Please specify only one.')

        # Device-aware parsing state
        self.devices = {}
        self.device_types = {}
        self.type_converters = {}

        # Metadata state
        self.metadata = metadata or {}
        self.metadata_interval = metadata_interval
        self.metadata_last_sent = {}

        # If field patterns not provided, look them up in definitions
        if field_patterns is None and definition_path is not None:
            field_patterns = self._load_definitions(definition_path)

            # If metadata not explicitly provided, compile it from definitions
            if not metadata and metadata_interval:
                self._compile_metadata()

        self.field_patterns = field_patterns

        # If we've been explicitly given the field_patterns we're to use for
        # parsing, compile them now.
        if field_patterns:
            if isinstance(field_patterns, list):
                self.compiled_field_patterns = [
                    re.compile(pattern)
                    for pattern in field_patterns
                ]
            elif isinstance(field_patterns, dict):
                self.compiled_field_patterns = {
                    message_type: re.compile(pattern)
                    for (message_type, pattern) in field_patterns.items()
                }
            else:
                raise ValueError('field_patterns must either be a list of patterns or '
                                 'dict of message_type:pattern pairs. Found type '
                                 f'{type(field_patterns)}')
        else:
            self.compiled_field_patterns = None

    ############################
    def _load_definitions(self, definition_path):
        """Load device definitions and return aggregated field patterns.
        Populates self.devices and self.device_types.
        """
        field_patterns = {}

        # Use shared utility to load definitions
        definitions = load_definitions(definition_path)

        # Store devices
        self.devices = definitions.get('devices', {})

        # Process device_types: store them, extract patterns, create converters
        for dt_name, dt_def in definitions.get('device_types', {}).items():
            self.device_types[dt_name] = dt_def

            # Aggregate formats (regexes)
            dt_formats = dt_def.get('format', {})
            if isinstance(dt_formats, dict):
                field_patterns.update(dt_formats)

            # Create cached component converter for this type
            dt_fields = dt_def.get('fields', {})
            if dt_fields and ConvertFieldsTransform:
                self.type_converters[dt_name] = ConvertFieldsTransform(
                    fields=dt_fields,
                    quiet=self.quiet
                )

        return field_patterns

    ############################
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

    ############################
    def parse_record(self, record):
        """Parse an id-prefixed text record into a DASRecord.
        """
        if not record:
            return None
        if not isinstance(record, str):
            logging.info('Record is not a string: "%s"', record)
            return None
        try:
            parsed_record = self.compiled_record_format.match(record).groupdict()
        except (ValueError, AttributeError):
            if not self.quiet:
                logging.warning('Unable to parse record into "%s"', self.record_format)
                logging.warning('Record: %s', record)
            return None

        if parsed_record is None:
            return None

        # Logic to determine data_id:
        # 1. If self.data_id is set (in __init__), use it (Override).
        # 2. Else, look for 'data_id' extracted from the record via regex.
        # 3. If that fails, default to 'unknown'.
        if self.data_id:
            data_id = self.data_id
        else:
            data_id = parsed_record.get('data_id', None)
            if not data_id:
                if not self.quiet:
                    logging.warning('No data_id found in record and none specified. '
                                    'Defaulting to "unknown".')
                data_id = 'unknown'

        # Convert timestamp to numeric, if it's there.
        # Initialize to None first to avoid UnboundLocalError if 'timestamp'
        # is not in the regex groups.
        timestamp = None
        timestamp_text = parsed_record.get('timestamp', None)

        if timestamp_text is not None:
            timestamp = self.convert_timestamp(timestamp_text)

        # If no timestamp found, DASRecord will default to time.time()
        # if passed None.
        if timestamp is None:
            timestamp = time.time()

        # Extract the field string we're going to parse;
        # remove trailing whitespace.
        field_string = parsed_record.get('field_string', None)
        if field_string is not None:
            field_string = field_string.rstrip()

        message_type = None
        fields = {}
        if field_string:
            # If we've been given a set of field_patterns to apply,
            # use the first that matches.
            # Shortcut that lets us iterate through a list or a dict with the same
            # invocation. With a list, it returns (None, value); with a dict it
            # returns (key, value).
            def iterate_patterns(obj):
                return (obj.items() if isinstance(obj, dict) else ((None, v) for v in obj))

            if self.field_patterns:
                for message_type, pattern in iterate_patterns(self.compiled_field_patterns):
                    try:
                        try_parse = pattern.match(field_string)
                        # Did we find a parse that matched?
                        # If so, return its fields
                        if try_parse:
                            fields = try_parse.groupdict()
                            break
                    except Exception as e:
                        logging.error(e)

        logging.debug('Created parsed fields: %s', pprint.pformat(fields))

        # Create the initial DASRecord
        try:
            das_record = DASRecord(data_id=data_id, timestamp=timestamp,
                                   message_type=message_type,
                                   fields=fields)
        except KeyError:
            return None

        # Device-Specific Processing
        # Try to match data_id to a known device
        if data_id in self.devices:
            device_def = self.devices[data_id]
            device_type = device_def.get('device_type')

            # A. Type Conversion (delegated to cached ConvertFieldsTransform)
            if device_type in self.type_converters:
                converter = self.type_converters[device_type]
                das_record = converter.transform(das_record)
                if not das_record:
                    return None

            # B. Field Renaming / Filtering
            # Only retain fields that are in the device's 'fields' map
            device_fields_map = device_def.get('fields', {})
            if device_fields_map:
                new_fields = {}
                for original_name, mapped_name in device_fields_map.items():
                    if original_name in das_record.fields:
                        # Use the mapped name (value)
                        new_fields[mapped_name] = das_record.fields[original_name]

                das_record.fields = new_fields

        # Metadata Injection
        # If we have parsed fields, see if we also have metadata. Are we
        # supposed to occasionally send it for our variables? Is it time
        # to send it again?
        metadata_to_inject = collect_metadata_for_fields(
            das_record.fields,
            das_record.timestamp or 0,
            self.metadata,
            self.metadata_interval,
            self.metadata_last_sent
        )
        if metadata_to_inject:
            if das_record.metadata is None:
                das_record.metadata = {}
            das_record.metadata['fields'] = metadata_to_inject['fields']

        return das_record

    ############################
    def convert_timestamp(self, datetime_text):
        """Validates a datetime string and converts to numeric.
        """

        DEFAULT_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'

        try:
            datetime_ti = datetime.datetime.strptime(
                datetime_text, DEFAULT_FORMAT)
        except ValueError:
            logging.debug("Incorrect datetime format.")
            return None

        if datetime_ti:
            # Explicitly set UTC timezone because the format expects 'Z'
            # .replace(tzinfo=...) ensures .timestamp() treats it as UTC
            # regardless of the local system clock.
            timestamp = datetime_ti.replace(tzinfo=datetime.timezone.utc).timestamp()
            return timestamp
