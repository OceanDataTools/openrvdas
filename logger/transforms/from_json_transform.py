#!/usr/bin/env python3

import json
import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
#
class FromJSONTransform(Transform):
    """Convert passed JSON to either a DASRecord or a dict.
    """

    def __init__(self, das_record=False):
        """Parse the received JSON and convert to appropriate data
        structure. If das_record == True, assume we've been passed a dict
        of field:value pairs, and try to embed them into a DASRecord.
        """
        self.das_record = das_record

    ############################
    def transform(self, record: str):
        """Parse JSON record to Python data struct or DASRecord."""

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            return self.digest_record(record)  # inherited from BaseModule()

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
