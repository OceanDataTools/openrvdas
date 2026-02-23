#!/usr/bin/env python3
"""Utilities for converting field values to specified types."""

import logging

# Map string type names to actual python types/conversion functions.
# Recognized types include:
#   float, double -> float
#   int, short, ushort, uint, long, ubyte, byte, hex_int -> int
#   str, char, string, text -> str
#   bool, boolean -> bool
TYPE_MAP = {
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
    'hex_int': lambda x: int(str(x), 16),  # Handles "1A", "0x1A", etc.
}


def convert_lat_lon(value, direction, rounding_decimals=5):
    """
    Convert NMEA style lat/lon (DDMM.MMMM) and direction (N/S/E/W)
    to decimal degrees.

    Args:
        value: NMEA format value (e.g., "4807.038" for 48°07.038')
        direction: Cardinal direction ('N', 'S', 'E', 'W')
        rounding_decimals: Number of decimal places to round to

    Returns:
        Decimal degrees as float, or None if conversion fails
    """
    try:
        val = float(value)
        # NMEA format is roughly DDMM.MMMM
        # Degrees is the integer part of val / 100
        degrees = int(val / 100)
        minutes = val - (degrees * 100)
        decimal = degrees + (minutes / 60)

        if direction.upper() in ['S', 'W']:
            decimal = -decimal

        return round(decimal, rounding_decimals)
    except (ValueError, TypeError, AttributeError) as e:
        logging.warning(f'Failed to convert lat/lon: value=\'{value}\', '
                        f'direction=\'{direction}\' - {e}')
        return None


def convert_field_value(value, target_type_str, quiet=False):
    """
    Convert a single field value to the specified type.

    Args:
        value: The value to convert
        target_type_str: String name of target type (e.g., 'float', 'int', 'str')
        quiet: If True, suppress warning messages

    Returns:
        Converted value, or original value if conversion fails
    """
    converter = TYPE_MAP.get(target_type_str)
    if not converter:
        if not quiet:
            logging.warning(f'Unknown type \'{target_type_str}\' requested')
        return value

    try:
        # Special case to head off ValueError of int("123.0")
        if isinstance(value, str) and converter is int:
            try:
                value = float(value)
            except ValueError:
                # Not a float string, let int() call below handle/fail it naturally
                pass

        return converter(value)
    except ValueError:
        if not quiet:
            logging.warning(f'Failed to convert value \'{value}\' '
                            f'(type={type(value).__name__}) to \'{target_type_str}\'')
        return value


def convert_fields(fields, field_specs, lat_lon_specs=None,
                   delete_source_fields=False, delete_unconverted_fields=False,
                   quiet=False):
    """
    Convert fields in a dictionary according to specifications.

    This is a shared utility used by ConvertFieldsTransform and can be used
    directly by parsers for field conversion.

    Args:
        fields: Dict of field_name -> value (modified in place)
        field_specs: Dict of field_name -> target_type or {data_type: target_type}
        lat_lon_specs: Dict of target_field -> (value_field, direction_field)
                      for NMEA lat/lon conversion
        delete_source_fields: If True, remove source fields after lat/lon conversion
        delete_unconverted_fields: If True, remove fields not involved in conversion
        quiet: If True, suppress warning messages

    Returns:
        The modified fields dict, or None if no fields remain after processing
    """
    if not fields:
        return None

    # Track which fields were successfully converted or used
    processed_fields = set()

    # 1. Handle simple Type Conversions
    if field_specs:
        for field_name, field_def in field_specs.items():
            if field_name not in fields:
                continue

            # Extract target type from dict, or use string directly
            if isinstance(field_def, dict):
                target_type_str = field_def.get('data_type')
            elif isinstance(field_def, str):
                target_type_str = field_def
            else:
                continue

            if not target_type_str:
                continue

            val = fields[field_name]
            converter = TYPE_MAP.get(target_type_str)
            if converter:
                try:
                    # Special case to head off ValueError of int("123.0")
                    if isinstance(val, str) and converter is int:
                        try:
                            val = float(val)
                        except ValueError:
                            pass

                    fields[field_name] = converter(val)
                    processed_fields.add(field_name)
                except ValueError:
                    if not quiet:
                        logging.warning(f'Failed to convert field \'{field_name}\': '
                                        f'value=\'{val}\' (type={type(val).__name__}) '
                                        f'to target_type=\'{target_type_str}\'')
            else:
                if not quiet:
                    logging.warning(f'Unknown type \'{target_type_str}\' '
                                    f'requested for field \'{field_name}\'')

    # 2. Handle Lat/Lon Conversions
    if lat_lon_specs:
        for target_field, (val_field, dir_field) in lat_lon_specs.items():
            if val_field not in fields or dir_field not in fields:
                continue

            val = fields[val_field]
            direction = fields[dir_field]

            decimal_degrees = convert_lat_lon(val, direction)

            if decimal_degrees is not None:
                fields[target_field] = decimal_degrees
                processed_fields.add(target_field)

                # Mark source fields as processed
                if delete_source_fields:
                    processed_fields.add(val_field)
                    processed_fields.add(dir_field)

                    # Delete source fields, but NOT if source == target
                    if val_field in fields and val_field != target_field:
                        del fields[val_field]
                    if dir_field in fields and dir_field != target_field:
                        del fields[dir_field]

    # 3. Clean up unconverted fields
    if delete_unconverted_fields:
        all_fields = list(fields.keys())
        for f in all_fields:
            if f not in processed_fields:
                del fields[f]

    # If no fields remain, return None
    if not fields:
        return None

    return fields
