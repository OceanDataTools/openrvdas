#!/usr/bin/env python3

import logging
import sys

from typing import Union
from os.path import dirname, realpath
from json import JSONDecodeError

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
#
class ToDASRecordTransform(Transform):
    """Convert passed record to DASRecord. If record is a str, assume a
    JSON-encoded DASRecord. If record is a dict, use its fields as DASRecord
    fields. If initialized with a field_name, expect to be passed strings,
    and use those strings as the corresponding field values.
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

        if isinstance(record, str):
            # If str, assume it's JSON unless field_name is set
            if self.field_name:
                return DASRecord(data_id=self.data_id, fields={self.field_name: record})
            else:
                try:
                    return DASRecord(record)
                except JSONDecodeError:
                    logging.warning(f'String could not be parsed as JSON DASRecord: {record}')
                    return None
        # Else, if it's a dict use keys, values as fields
        elif isinstance(record, dict):
            return DASRecord(data_id=self.data_id, fields=record)
        else:
            logging.warning('ToDASRecordTransform input should be of type '
                            f'str or dict, but received {type(record)}: {record}')
            return None
