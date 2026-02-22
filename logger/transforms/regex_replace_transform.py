#!/usr/bin/env python3

import re
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class RegexReplaceTransform(Transform):
    """Apply regex replacements to record."""
    ############################

    def __init__(self, patterns, count=0, flags=0, **kwargs):
        """
        patterns - a dict of {old:new, old:new} patterns to be searched and replaced.
                   Note that replacement order is not guaranteed.
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        self.patterns = patterns
        self.count = count
        self.flags = flags

    ############################
    def transform(self, record: str) -> str:
        """Does record contain pattern?"""

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            return self.digest_record(record)  # inherited from BaseModule()

        # Apply all patterns in order
        result = record
        for old_str, new_str in self.patterns.items():
            # FIX: Pass count and flags as keyword arguments to avoid DeprecationWarning
            result = re.sub(old_str, new_str, result, count=self.count, flags=self.flags)
        return result
