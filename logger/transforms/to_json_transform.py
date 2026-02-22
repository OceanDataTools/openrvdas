#!/usr/bin/env python3

import json
import logging
import sys

from typing import Union
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
#
class ToJSONTransform(Transform):
    """Convert passed DASRecords, lists or dicts to JSON. If pretty == True,
    format the JSON output for easy reading.
    """

    ############################
    def __init__(self, pretty=False, **kwargs):
        super().__init__(**kwargs)  # processes 'quiet' and type hints
        self.pretty = pretty

    ############################
    def transform(self, record: Union[DASRecord, float, int, bool, str, dict, list, set]) -> str:
        """Convert record to JSON."""

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            return self.digest_record(record)  # inherited from BaseModule()

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
