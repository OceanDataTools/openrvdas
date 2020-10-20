#!/usr/bin/env python3
"""Compute subsamples of input data.
"""

import copy
import logging
import sys


from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class SelectFieldsTransform(Transform):
    """Cull key:value pairs from a record's field dict. Can accept a
    top-level dict, a field dict or a DASRecord, and will return a
    record in the same format as it received.
    """

    def __init__(self, keep=None, delete=None):
        """

        ```
        keep - an optional list of field names to keep

        delete - an optional list of field names to delete

        One, but not both of these should be present. If both are present,
        the delete values will be ignored.

        Can accept a top-level dict, a field dict or a DASRecord, and will
        return a record in the same format as it received.
        ```

        """
        self.keep = keep or []
        self.delete = delete or []

        if not keep and not delete:
            logging.warning('SelectFieldsTransform has empty "keep" and "delete" arguments; '
                            'no modifications will be made to passed records.')
        if keep and delete:
            logging.warning('SelectFieldsTransform has both "keep" and "delete" arguments; '
                            '"delete" arguments will be ignored.')

    ############################
    def transform(self, record):
        """
        Return a copy of the passed record with the relevant fields kept/deleted.
        """

        # We need to make a deep copy of the record, because we're going
        # to modify it as we go, and the same record may be getting passed
        # to multiple transforms at the same time (e.g., if the transform
        # is part of a ComposedWriter, and we have multiple
        # ComposedWriters).
        new_record = copy.deepcopy(record)

        # Below, we're counting on Python copying the relevant dict by
        # reference so that if we modify the 'fields' dict, it is also
        # modified in the record we were passed.

        # As warned in the constructor, if we have both keep and delete,
        # we're going to pass records through unchanged.
        if self.keep and self.delete:
            return new_record

        # If we've got a list, hope it's a list of records. Try to add
        # them all.
        if type(new_record) is list:
            new_record_list = []
            for single_new_record in new_record:
                new_record_list.append(self.transform(single_new_record))
            return new_record_list

        # If it's a dict, hope it's a single record.
        elif type(new_record) is DASRecord:
            fields = new_record.fields

        elif type(new_record) is dict:
            # If we have a 'fields' dict inside the dict, use that
            if 'fields' in new_record and type(new_record['fields']) is dict:
                fields = new_record['fields']

            # Otherwise treat the entire dict as a field dict
            else:
                fields = new_record

        else:
            logging.warning('SelectFieldsTransform Got non-list/dict/DASRecord '
                            'record to interpolate: %s', new_record)
            return None

        if self.delete:
            for key in self.delete:
                if key in fields:
                    del fields[key]
        else:
            field_list = list(fields.keys())
            for key in field_list:
                if key not in self.keep:
                    del fields[key]

        # If no fields left, scrap the record
        if not fields:
            return None

        return new_record
