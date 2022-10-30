#!/usr/bin/env python3

import logging
import re
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class RegexReplaceTransform(Transform):
    """Apply regex replacements to record."""
    ############################

    def __init__(self, patterns, count=0, flags=0):
        """
        patterns - a dict of {old:new, old:new} patterns to be searched and replaced.
                   Note that replacement order is not guaranteed.
        """
        super().__init__(input_format=formats.Text, output_format=formats.Text)

        self.patterns = patterns
        self.count = count
        self.flags = flags

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

        # Apply all patterns in order
        result = record
        for old_str, new_str in self.patterns.items():
            result = re.sub(old_str, new_str, result, self.count, self.flags)
        return result
