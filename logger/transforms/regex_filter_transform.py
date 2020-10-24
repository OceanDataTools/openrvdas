#!/usr/bin/env python3

import re
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class RegexFilterTransform(Transform):
    """Only return records matching the specified regular expression."""
    ############################

    def __init__(self, pattern, flags=0, negate=False):
        """If negate=True, only return records that *don't* match the pattern."""
        super().__init__(input_format=formats.Text, output_format=formats.Text)
        self.pattern = re.compile(pattern, flags)
        self.negate = negate

    ############################
    def transform(self, record):
        """Does record contain pattern?"""
        if not record:
            return None

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list.
        if type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record))
            return results

        match = self.pattern.search(record)
        if match is None:
            if self.negate:
                return record
            return None
        else:
            if self.negate:
                return None
            return record
