#!/usr/bin/env python3
"""Pass the record to the next transform/writer only if the contents of the
record have changed from the previous value.
"""

import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class UniqueTransform(Transform):
    """Return the record only if it has changed from the previous value."""

    def __init__(self):
        """Starts with an empty record."""
        self.prev_record = ""

    ############################
    def transform(self, record: str):

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from Transform()
            return self.digest_record(record)  # inherited from Transform()

        """If same as previous, return None, else record."""
        if record == self.prev_record:
            return None

        self.prev_record = record

        return record
