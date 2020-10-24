#!/usr/bin/env python3

import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class PrefixTransform(Transform):
    """Prepend a prefix to a text record."""

    def __init__(self, prefix, sep=' '):
        """Use space as default separator."""
        super().__init__(input_format=formats.Text, output_format=formats.Text)
        self.prefix = prefix + sep

    ############################
    def transform(self, record):
        """Prepend a prefix."""
        if record is None:
            return None

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list.
        if type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record))
            return results

        return self.prefix + record
