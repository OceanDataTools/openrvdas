#!/usr/bin/env python3

import logging
import sys

from typing import Union
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
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
        self.data_id = data_id
        self.field_name = field_name

    ############################
    def transform(self, record: Union[str, dict]):
        """Convert record to DASRecord."""

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from Transform()
            return self.digest_record(record)  # inherited from Transform()

        if self.field_name:
            if type(record) is str:
                das_record = DASRecord(data_id=self.data_id, fields={self.field_name: record})
                return das_record
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
