#!/usr/bin/env python3
"""Split a single record at a delimiter string, into an array of records."""

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.base_transform import BaseTransform  # noqa: E402


################################################################################
class SplitTransform(BaseTransform):
    def __init__(self, sep='\n'):
        """
        ```
        sep       Field separator string; if omitted, split along newlines.
        ```
        """
        self.sep = sep

    ############################
    def _transform_single_record(self, record):
        """Split record into array of records along separator."""
        if not type(record) is str:
            logging.warning('SplitTransform received non-string input: %s', record)
            results = None

        # If here, we've got a simple string.
        else:
            results = record.split(self.sep)

        return [record for record in results if record]
