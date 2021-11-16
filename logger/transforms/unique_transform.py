#!/usr/bin/env python3
"""Pass the record to the next transform/writer only if the contents of the
record have changed from the previous value.
"""

import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class UniqueTransform(Transform):
    """Return the record only if it has changed from the previous value."""

    def __init__(self):
        """Starts with an empty record."""
        super().__init__(input_format=formats.Text, output_format=formats.Text)
        self.prev_record = ""

    ############################
    def transform(self, record):
        """If same as previous, return None, else record."""
        if record == self.prev_record:
            return None

        self.prev_record = record

        return record
