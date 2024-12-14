#!/usr/bin/env python3
"""Modify values according to simple formula
"""

import copy
import logging
import sys
import time

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.derived_data_transform import DerivedDataTransform  # noqa: E402


################################################################################
class ModifyValueTransform(DerivedDataTransform):
    """Modify the value of specified fields according to simple formulae.
    """

    def __init__(self, fields, delete_unmatched=False, quiet=False,
                 metadata_interval=None):
        """
        fields - a dict of fields to match.

            fields:
              FieldName:
                mult_factor:  1.5   # default 1.0
                add_factor: 3.44  # default 0.0
                output_name: CorrectedFieldName  # default is FieldName
                metadata: Field name with linear foobar correction applied
                delete_original: true  # default false
              FieldName2:
                mapping_function: my_magic_function  # God knows how we'd implement this, but...
                output_name: CorrectedFieldName2
              ....

              Key of each is the field to match. Values are a dict of what to do with
              the value, including:
                mult_factor (default=1), add_factor (default=0)
                  result = mult_factor * value + add_factor

                output_name (default is original field name)
                  Add the result to the record as a new field

                delete_original (default=False)
                  If true, and if output_name is specified, delete original field from record

                metadata (default=None)
                  If specified, any metadata associated with the new value

        delete_unmatched (default=False)
          If true, delete any unmatched fields from the record

        quiet (default=False)
          If True, don't warn if can't convert, or overwriting existing values

        metadata_interval (default=None)
          If not None, how frequently, in seconds to attach field metadata to records
          (NOTE: need to address which fields' metadata is sent along - all specified,
          or only fields that have appeared since last send, or...?)
        """
        self.fields = fields
        self.delete_unmatched = delete_unmatched
        self.quiet = quiet
        self.metadata_interval = metadata_interval or 0

        self._validate_fields()
        self.last_metadata_send = 0
        self.metadata = {
            field: spec.get('metadata')
            for field, spec in fields.items() if spec.get('metadata')
        }

    ############################
    def _validate_fields(self):
        """Validate the configuration of fields."""
        allowed_keys = {'mult_factor', 'add_factor', 'output_name', 'metadata', 'delete_original'}

        for field, spec in self.fields.items():
            extraneous_keys = set(spec) - allowed_keys
            if extraneous_keys:
                raise ValueError(f'Unexpected keys in field "{field}": {extraneous_keys}. '
                                 f'Allowed keys are {allowed_keys}')

            if not isinstance(spec.get('mult_factor', 1), (int, float)):
                raise ValueError(f'Invalid "mult_factor" for field "{field}". Must be numeric.')
            if not isinstance(spec.get('add_factor', 0), (int, float)):
                raise ValueError(f'Invalid "add_factor" for field "{field}". Must be numeric.')

    ############################
    def transform(self, record):
        """
        Transform a record or list of records.

        Args:
            record (DASRecord or list): The input record(s).

        Returns:
            Transformed record(s) or None if the input is invalid.
        """
        # If we've got a list, hope it's a list of records. Try to add
        # them all.
        if type(record) is list:
            result_list = [self.transform(single_record) for single_record in record]
            return [r for r in result_list if r is not None]

        if not isinstance(record, DASRecord):
            logging.warning(f'ModifyValueTransform received non-DASRecord: {type(record)}')
            logging.warning(f'{record}')
            return None

        # Make a copy of the original record we're going to munge
        result = copy.deepcopy(record)

        # More efficient, but doesn't allow use to do delete_unmatched:
        # for field in record.fields.keys() & self.fields.keys():
        for field in record.fields:
            field_spec = self.fields.get(field)

            # If there isn't a rule for this field
            if field_spec is None:
                if self.delete_unmatched:
                    del result[field]
                continue

            # Get the field value, make sure we can work with it
            value = record.get(field)
            try:
                value = float(value)
            except ValueError:
                if not self.quiet:
                    logging.warning(f'ModifyValueTransform could not convert field {field} value '
                                    f'"{value}" to float for modification. Type: {type(value)}')
                continue

            # Do the actual computation
            value *= field_spec.get('mult_factor', 1.0)
            value += field_spec.get('add_factor', 0.0)

            # Where are we going to write the value? Check if it already exists. If there is no
            # target field name, use original field name.
            target_field = field_spec.get('output_name')
            if target_field and target_field in record.fields and not self.quiet:
                logging.warning(f'ModifyValueTransform overwriting existing field: {target_field}')
            if not target_field:
                target_field = field

            # Are we getting rid of the original field? If so, do that now, to avoid
            # the semantic question of deleting original value when we're writing back
            # to original field
            if field_spec.get('delete_original'):
                del result[field]

            result[target_field] = value

        # We're now done going through the record fields. If it's time to send metadata,
        # add it to any existing metadata for record, overwriting existing fields.
        if self._should_attach_metadata(record):
            result.metadata.update(self.metadata)

        return result

    ############################
    def _should_attach_metadata(self, record):
        """Determine if metadata should be attached to the record."""
        now = record.timestamp or time.time()
        if self.metadata_interval and now > self.last_metadata_send + self.metadata_interval:
            self.last_metadata_send = now
            return True
        return False
