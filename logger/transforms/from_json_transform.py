#!/usr/bin/env python3

import json
import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.base_transform import BaseTransform  # noqa: E402


################################################################################
#
class FromJSONTransform(BaseTransform):
    """Convert passed JSON to either a DASRecord or a dict.
    """

    def __init__(self, das_record=False):
        """Parse the received JSON and convert to appropriate data
        structure. If das_record == True, assume we've been passed a dict
        of field:value pairs, and try to embed them into a DASRecord.
        """
        super().__init__(input_format=formats.Python_Record,
                         output_format=formats.Text)

        self.das_record = das_record

    ############################
    def _transform_single_record(self, record):
        """Parse JSON record to Python data struct or DASRecord."""
        if not type(record) is str:
            logging.warning('FromJSON transform received non-string input, '
                            'type: "%s"', type(record))
            return None

        try:
            data = json.loads(record)
        except json.decoder.JSONDecodeError:
            logging.warning('Failed to parse JSON string: "%s"', record)
            return None

        if not self.das_record:
            return data

        if not type(data) is dict:
            logging.warning('FromJSON asked to create DASRecord from non-dict '
                            'data: "%s"', type(data))
            return None

        return DASRecord(fields=data)
