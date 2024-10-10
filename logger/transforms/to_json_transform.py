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
class ToJSONTransform(BaseTransform):
    """Convert passed DASRecords, lists or dicts to JSON. If pretty == True,
    format the JSON output for easy reading.
    """

    def __init__(self, pretty=False):
        super().__init__(input_format=formats.Python_Record,
                         output_format=formats.Text)

        self.pretty = pretty

    ############################
    def _transform_single_record(self, record):
        """Convert record to JSON."""
        if type(record) is DASRecord:
            return record.as_json(self.pretty)

        if type(record) in [float, int, bool, str, dict, list, set]:
            if self.pretty:
                return json.dumps(record, sort_keys=True, indent=4)
            else:
                return json.dumps(record)

        logging.warning('ToJSON transform received record format it could not '
                        'serialize: "%s"', type(record))
        return None
