#!/usr/bin/env python3

import re
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.transforms.base_transform import BaseTransform  # noqa: E402


################################################################################
class RegexFilterTransform(BaseTransform):
    """Only return records matching the specified regular expression."""
    ############################

    def __init__(self, pattern, flags=0, negate=False):
        """If negate=True, only return records that *don't* match the pattern."""
        super().__init__(input_format=formats.Text, output_format=formats.Text)
        self.pattern = re.compile(pattern, flags)
        self.negate = negate

    ############################
    def _transform_single_record(self, record):
        """Does record contain pattern?"""
        match = self.pattern.search(record)
        if match is None:
            if self.negate:
                return record
            return None
        else:
            if self.negate:
                return None
            return record
