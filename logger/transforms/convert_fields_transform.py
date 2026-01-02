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

    def __init__(self, fields=None, lat_lon_fields=None,
                 delete_source_fields=False, delete_unconverted_fields=False):
        """
        Args:
            fields (dict): A dictionary mapping field names to their target types.
                           Supported types are 'float', 'int', 'str'.
                           Example: {'heave': 'float', 'pitch': 'float'}

            lat_lon_fields (dict): A dictionary mapping a new target field name to a tuple
                                   or list of (value_field, direction_field).
                                   Example:
                                   {'latitude': ('raw_lat', 'lat_dir'),
                                    'longitude': ('raw_lon', 'lon_dir')}

            delete_source_fields (bool): If True, the original source fields used for
                                         conversion (like 'raw_lat' and 'lat_dir')
                                         are removed after successful conversion.
                                         Defaults to False.

            delete_unconverted_fields (bool): If True, any field in the record that was
                                              NOT involved in a conversion (either as a
                                              source or a destination) will be removed.
                                              Defaults to False.
        """
        self.fields = fields or {}
        self.lat_lon_fields = lat_lon_fields or {}
        self.delete_source_fields = delete_source_fields
        self.delete_unconverted_fields = delete_unconverted_fields

        # Map string type names to actual python types/conversion functions
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
            'boolean': bool
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
    def transform(self, record: Union[str, dict]):
        """
        Return a copy of the passed record with fields converted.
        """
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
        for field_name, target_type_str in self.fields.items():
            if field_name in fields:
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
