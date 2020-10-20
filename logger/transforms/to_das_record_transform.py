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
class ToDASRecordTransform(Transform):
    """Convert passed record to DASRecord. If initialized with a
    field_name, expect to be passed strings, and use those strings as
    the corresponding field values. Otherwise, expect a dict, and use it
    as the DASRecord's fields.
    """

    def __init__(self, data_id=None, field_name=None):
        super().__init__(input_format=formats.Bytes,
                         output_format=formats.Python_Record)
        self.data_id = data_id
        self.field_name = field_name

    ############################
    def transform(self, record):
        """Convert record to DASRecord."""
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

        if self.field_name:
            if type(record) is str:
                return DASRecord(data_id=self.data_id, fields={self.field_name: record})
            else:
                logging.warning('When ToDASRecordTransform is initialized with '
                                'field_name ("%s"), inputs should be of type str, '
                                'but received input of type "%s": %s',
                                self.field_name, type(record), record)
                return None
        else:
            if type(record) is dict:
                return DASRecord(data_id=self.data_id, fields=record)
            else:
                logging.warning('When ToDASRecordTransform is initialized without '
                                'field_name, inputs should be of type dict, but '
                                'received input of type "%s": %s', type(record), record)
                return None
