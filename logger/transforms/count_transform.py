#!/usr/bin/env python3

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
#
class CountTransform(Transform):
    """Return number of times the passed fields have been seen as a dict
    (or DASRecord, depending on what was passed in) where the keys are
    'field_name:count' and the values are the number of times the passed
    in fields have been seen. E.g:
    ```
    counts = CountTransform()
    counts.transform({'f1': 1, 'f2': 1.5}) -> {'f1:count':1, 'f2:count':1}
    counts.transform({'f1': 1}) -> {'f1:count':2}
    counts.transform({'f1': 1.1, 'f2': 1.4}) -> {'f1:count':3, 'f2:count':2}
    ```
    """

    def __init__(self):
        """
        """
        super().__init__(input_format=formats.Python_Record,
                         output_format=formats.Text)
        self.counts = {}

    ############################
    def transform(self, record):
        """Return counts of the previous times we've seen these field names."""
        if not record:
            return None

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list.
        if type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record))
            return results

        if type(record) is DASRecord:
            fields = record.fields
        elif type(record) is dict:
            fields = record
        else:
            logging.warning('Input to CountTransform must be either '
                            'DASRecord or dict. Received type "%s"', type(record))
            return None

        new_counts = {}

        for field, value in fields.items():
            if field not in self.counts:
                self.counts[field] = 1
            else:
                self.counts[field] += 1
            new_counts[field + ':count'] = self.counts[field]

        if type(record) is DASRecord:
            if record.data_id:
                data_id = record.data_id + '_counts' if record.data_id else 'counts'
            return DASRecord(data_id=data_id,
                             message_type=record.message_type,
                             timestamp=record.timestamp,
                             fields=new_counts)

        return new_counts
