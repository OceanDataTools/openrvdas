#!/usr/bin/env python3
"""Split a single record at a delimiter string, into an array of records."""

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class SplitTransform(Transform):
    def __init__(self, sep='\n', **kwargs):
        """
        ```
        sep       Field separator string; if omitted, split along newlines.
        ```
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints
        self.sep = sep

    ############################
    def transform(self, record: str) -> list:
        """Split record into array of records along separator."""

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            return self.digest_record(record)  # inherited from BaseModule()

        if not type(record) is str:
            logging.warning('SplitTransform received non-string input: %s', record)
            results = None

        # If here, we've got a simple string.
        else:
            results = record.split(self.sep)

        return [record for record in results if record]
