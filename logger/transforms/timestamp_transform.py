#!/usr/bin/env python3

import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.utils import timestamp  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
"""Prepend a timestamp to a text record."""


class TimestampTransform(Transform):
    def __init__(self, time_format=timestamp.TIME_FORMAT,
                 time_zone=timestamp.timezone.utc, sep=' '):
        """If timestamp_format is not specified, use default format"""
        super().__init__(input_format=formats.Text, output_format=formats.Text)
        self.time_format = time_format
        self.time_zone = time_zone
        self.sep = sep

    ############################
    def transform(self, record, ts=None):
        """Prepend a timestamp"""
        if record is None:
            return None

        # First off, grab a current timestamp
        ts = ts or timestamp.time_str(time_format=self.time_format,
                                      time_zone=self.time_zone)

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list. Give each element the same timestamp.
        if type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record, ts=ts))
            return results

        return ts + self.sep + record
