#!/usr/bin/env python3
"""Split a single record at a delimiter string, into an array of records."""

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class SplitTransform(Transform):
    def __init__(self, sep='\n'):
        """
        ```
        sep       Field separator string; if omitted, split along newlines.
        ```
        """
        self.sep = sep

    ############################
    def transform(self, record):
        """Split record into array of records along separator."""
        if record is None:
            return None

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list.
        if type(record) is list:
            results = []
            for single_record in record:
                results += self.transform(single_record)

        elif not type(record) is str:
            logging.warning('SplitTransform received non-string input: %s', record)
            results = None

        # If here, we've got a simple string.
        else:
            results = record.split(self.sep)

        return [record for record in results if record]
