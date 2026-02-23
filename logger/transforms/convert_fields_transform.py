#!/usr/bin/env python3
"""Transform to convert fields in a DASRecord to specified types.

This is a thin wrapper around the convert_fields utility function,
providing the Transform interface for use in listener pipelines.
"""

import copy
import logging
import sys
from typing import Union

from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.utils.convert_fields import convert_fields  # noqa: E402
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

        self.field_specs = {}
        self.lat_lon_specs = {}
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
                        # Format: target_field -> (value_field, direction_field)
                        self.lat_lon_specs[f_name] = (f_name, dir_field)
                    else:
                        logging.warning(f"Field '{f_name}' has type '{dtype}' but "
                                        "missing 'direction_field'. Ignoring.")
                else:
                    # Standard field
                    self.field_specs[f_name] = f_def

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

        # Delegate to the utility function
        result = convert_fields(
            fields,
            self.field_specs,
            self.lat_lon_specs,
            delete_source_fields=self.delete_source_fields,
            delete_unconverted_fields=self.delete_unconverted_fields,
            quiet=self.quiet
        )

        # If no fields remain, return None
        if result is None:
            return None

        return new_record
