#!/usr/bin/env python3

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.base_transform import BaseTransform  # noqa: E402


################################################################################
#
class ExtractFieldTransform(BaseTransform):
    """Extract a field from passed DASRecord or dict.
    """

    def __init__(self, field_name):
        """Extract the specified field from the passed DASRecord or dict.
        """
        self.field_name = field_name

    ############################
    def _transform_single_record(self, record):
        """Extract the specified field from the passed DASRecord or dict.
        """
        if type(record) is DASRecord:
            return record.fields.get(self.field_name, None)
        elif type(record) is dict:
            fields = record.get('fields', None)
            if not fields:
                return None
            return fields.get(self.field_name, None)

        logging.warning('ExtractFieldTransform found no field "%s" in record "%s"',
                        self.field_name, record)
        return None
