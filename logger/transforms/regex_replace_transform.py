#!/usr/bin/env python3

import re
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.transforms.base_transform import BaseTransform  # noqa: E402


################################################################################
class RegexReplaceTransform(BaseTransform):
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
    def _transform_single_record(self, record):
        """Does record contain pattern?"""
        # Apply all patterns in order
        result = record
        for old_str, new_str in self.patterns.items():
            result = re.sub(old_str, new_str, result, self.count, self.flags)
        return result
