#!/usr/bin/env python3

import re
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class RegexFilterTransform(Transform):
    """Only return records matching the specified regular expression."""
    ############################

    def __init__(self, pattern, flags=0, negate=False, **kwargs):
        """If negate=True, only return records that *don't* match the pattern."""
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        self.pattern = re.compile(pattern, flags)
        self.negate = negate

    ############################
    def transform(self, record: str) -> str:
        """Does record contain pattern?"""

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            return self.digest_record(record)  # inherited from BaseModule()

        match = self.pattern.search(record)
        if match is None:
            if self.negate:
                return record
            return None
        else:
            if self.negate:
                return None
            return record
