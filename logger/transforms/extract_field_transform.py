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
class ExtractFieldTransform(Transform):
    """Extract a field from passed DASRecord or dict.
    """

    def __init__(self, field_name, **kwargs):
        """Extract the specified field from the passed DASRecord or dict.
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        self.field_name = field_name

    ############################
    def transform(self, record: Union[DASRecord, dict]):
        """Extract the specified field from the passed DASRecord or dict.
        """
        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # BaseModule
            return self.digest_record(record)  # BaseModule

        if type(record) is DASRecord:
            return record.fields.get(self.field_name)
        elif type(record) is dict:
            fields = record.get('fields')
            if not fields:
                return None
            return fields.get(self.field_name)

        logging.warning('ExtractFieldTransform found no field "%s" in record "%s"',
                        self.field_name, record)
        return None
