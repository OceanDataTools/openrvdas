#!/usr/bin/env python3

import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import timestamp  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class TimestampTransform(Transform):
    """Prepend a timestamp to a text record."""
    def __init__(self, time_format=timestamp.TIME_FORMAT,
                 time_zone=timestamp.timezone.utc, sep=' '):
        """If timestamp_format is not specified, use default format"""
        self.time_format = time_format
        self.time_zone = time_zone
        self.sep = sep

    ############################
    def transform(self, record: str, ts=None):
        """Prepend a timestamp"""

        # First off, grab a current timestamp
        ts = ts or timestamp.time_str(time_format=self.time_format,
                                      time_zone=self.time_zone)

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from Transform()
            # Special case: if we can't process it, but it's a list, pass
            # along the same initial timestamp so all elements in the list
            # share the same timestamp.
            if isinstance(record, list):
                return [self.transform(r, ts) for r in record]
            # If not str and not list, pass it along to digest_record()
            # to let it try and/or complain.
            else:
                return self.digest_record(record)  # inherited from Transform()

        # If it is something we can process, put a timestamp on it.
        return ts + self.sep + record
