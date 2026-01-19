#!/usr/bin/env python3
"""Convert fields in a DASRecord to specified types.
"""

import copy
import logging
import sys
from typing import Union

# Ensure we can import the necessary classes
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class ConvertFieldsTransform(Transform):
    """
    Converts fields in a DASRecord from strings (or other types) to specific types
    defined in a configuration dictionary. Also handles NMEA-style latitude/longitude
    conversions (e.g., combining a value and a cardinal direction field).
    """

    def __init__(self, fields=None, delete_source_fields=False,
                 delete_unconverted_fields=False, **kwargs):
        """
        Args:
            fields (dict): A dictionary mapping field names to their target configuration.
                           This accepts two formats for the value:
                           1. A dictionary containing metadata (preferred).
                              keys:
                                'data_type': target type (float, int, str, bool, hex,
                                             nmea_lat, nmea_lon)
                                'direction_field': (for nmea_*) name of direction field
                              Example:
                                  {'Latitude': {'data_type': 'nmea_lat',
                                                'direction_field': 'NorS'}}
                           2. A simple string specifying the data type (backward compatibility).
                              Example:
                                  {'heave': 'float'}

            delete_source_fields (bool): If True, source fields (e.g. 'raw_lat', 'lat_dir')
                                         are removed after successful conversion.
                                         Defaults to False.

            delete_unconverted_fields (bool): If True, fields NOT involved in conversion
                                              are removed. Defaults to False.
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        self.fields = {}
        self.lat_lon_fields = {}
        self.delete_source_fields = delete_source_fields
        self.delete_unconverted_fields = delete_unconverted_fields

        if fields:
            # Process fields to separate standard conversions from special NMEA ones
            for f_name, f_def in fields.items():
                # Normalize definition
                if isinstance(f_def, str):
                    f_def = {'data_type': f_def}

                dtype = f_def.get('data_type')

                # Check for declarative NMEA configuration
                if dtype in ['nmea_lat', 'nmea_lon']:
                    dir_field = f_def.get('direction_field')
                    if dir_field:
                        # Add to lat_lon_fields
                        # Format: target_field -> (value_field, direction_field)
                        # Here target_field is f_name.
                        # value_field is ALSO f_name (it's the raw string value before conversion).
                        # This works because transform() pulls the record value using key.
                        self.lat_lon_fields[f_name] = (f_name, dir_field)
                    else:
                        logging.warning(f"Field '{f_name}' has type '{dtype}' but "
                                        "missing 'direction_field'. Ignoring.")
                else:
                    # Standard field
                    self.fields[f_name] = f_def

        # Map string type names to actual python types/conversion functions.

        # Map string type names to actual python types/conversion functions.
        # Recognized types include:
        #   float, double -> float
        #   int, short, ushort, uint, long, ubyte, byte, hex -> int
        #   str, char, string, text -> str
        #   bool, boolean -> bool
        self.type_map = {
            'float': float,
            'double': float,
            'int': int,
            'short': int,
            'ushort': int,
            'uint': int,
            'long': int,
            'ubyte': int,
            'byte': int,
            'str': str,
            'char': str,
            'string': str,
            'text': str,
            'bool': bool,
            'boolean': bool,
            'hex': lambda x: int(str(x), 16),  # Handles "1A", "0x1A", etc.
        }

    ############################
    def _convert_lat_lon(self, value, direction):
        """
        Helper to convert NMEA style lat/lon (DDMM.MMMM) and direction (N/S/E/W)
        to decimal degrees, rounded to fixed number of decimal places.
        """
        ROUNDING_DECIMALS = 5
        try:
            val = float(value)
            # NMEA format is roughly DDMM.MMMM
            # Degrees is the integer part of val / 100
            degrees = int(val / 100)
            minutes = val - (degrees * 100)
            decimal = degrees + (minutes / 60)

            if direction.upper() in ['S', 'W']:
                decimal = -decimal

            # Truncate/Round
            return round(decimal, ROUNDING_DECIMALS)
        except (ValueError, TypeError, AttributeError) as e:
            logging.warning(f'Failed to convert lat/lon: value=\'{value}\', '
                            f'direction=\'{direction}\' - {e}')
            return None

    ############################
    def transform(self, record: Union[str, dict, DASRecord])\
            -> Union[str, dict, DASRecord]:
        """
        Return a copy of the passed record with fields converted.
        """
        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # BaseModule
            return self.digest_record(record)  # BaseModule

        # We need to make a deep copy because we modify the record in place
        new_record = copy.deepcopy(record)

        # Handle list of records
        if isinstance(new_record, list):
            new_record_list = []
            for single_record in new_record:
                result = self.transform(single_record)
                if result:
                    new_record_list.append(result)
            return new_record_list

        # Identify the fields dictionary
        if isinstance(new_record, DASRecord):
            fields = new_record.fields
        elif isinstance(new_record, dict):
            if 'fields' in new_record and isinstance(new_record['fields'], dict):
                fields = new_record['fields']
            else:
                fields = new_record
        else:
            logging.warning('ConvertFieldsTransform received unknown record type: %s',
                            type(new_record))
            return None

        # Track which fields were successfully converted or used
        processed_fields = set()

        # 1. Handle simple Type Conversions
        for field_name, field_def in self.fields.items():
            if field_name in fields:
                # Extract target type from dict, or fallback if string
                target_type_str = None
                if isinstance(field_def, dict):
                    target_type_str = field_def.get('data_type')
                elif isinstance(field_def, str):
                    target_type_str = field_def

                if not target_type_str:
                    continue

                val = fields[field_name]
                try:
                    converter = self.type_map.get(target_type_str)
                    if converter:
                        # Special case to head off ValueError of int("123.0")
                        if isinstance(val, str) and converter is int:
                            try:
                                val = float(val)
                            except ValueError:
                                # Not a float string, let int() call below handle/fail it naturally
                                pass

                        fields[field_name] = converter(val)
                        processed_fields.add(field_name)
                    else:
                        logging.warning(f'Unknown type \'{target_type_str}\' '
                                        f'requested for field \'{field_name}\'')
                except ValueError:
                    logging.warning(f'Failed to convert field \'{field_name}\': '
                                    f'value=\'{val}\' (type={type(val).__name__}) '
                                    f'to target_type=\'{target_type_str}\'')

        # 2. Handle Lat/Lon Conversions
        for target_field, (val_field, dir_field) in self.lat_lon_fields.items():
            if val_field in fields and dir_field in fields:
                val = fields[val_field]
                direction = fields[dir_field]

                decimal_degrees = self._convert_lat_lon(val, direction)

                if decimal_degrees is not None:
                    fields[target_field] = decimal_degrees
                    processed_fields.add(target_field)

                    # If we are successfully converting, we mark sources for potential deletion
                    if self.delete_source_fields:
                        # Mark them processed so they don't get deleted by unconverted check
                        processed_fields.add(val_field)
                        processed_fields.add(dir_field)

                        # Actually delete them now if configured, BUT...
                        # Do NOT delete if the source field is the same as the target field!
                        if val_field in fields and val_field != target_field:
                            del fields[val_field]
                        if dir_field in fields and dir_field != target_field:
                            del fields[dir_field]

        # 3. Clean up unconverted fields
        if self.delete_unconverted_fields:
            # We must create a list of keys since we are modifying the dict
            all_fields = list(fields.keys())
            for f in all_fields:
                if f not in processed_fields:
                    del fields[f]

        # If no fields remain, return None? Or empty record?
        # SelectFieldsTransform returns None if no fields left.
        if not fields:
            return None

        return new_record
