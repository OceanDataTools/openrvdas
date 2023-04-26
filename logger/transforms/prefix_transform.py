#!/usr/bin/env python3

import logging
import re
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class PrefixTransform(Transform):
    """Prepend a prefix to a text record."""

    def __init__(self, prefix, sep=' ', quiet=False):
        """Prepend the specified prefix to the record, using space as the default
        separator. If prefix is a <regex>:prefix map, go through in order and use
        the prefix of the first regex that matches. If no prefix matches, raise a
        warning (if quiet != True) and return None.

        Note: order of map evaluation is supposed to be guaranteed as of Python 3.7,
        but trust at your own risk.

        Note: the empty string '' as a regex will match all non-empty strings, so
        if you trust Python ordering, it can be used as a backstop default match for
        all records that don't match other strings.

        prefix    Either a simple string prefix or a dict mapping. If a string, it
                  will be used as the prefix. If a dict, it will be interpreted as
                  a <regex>:prefix mapping, and the prefix corresponding to the
                  first matching regex will be used. If no regex matches, None will
                  be returned.

        sep       A separator to be used between prefix and record.

        quiet     If true, do not log a warning if no regex matches.
        """
        if type(prefix) is str:
            self.prefix = prefix + sep
        elif type(prefix) is dict:
            self.prefix = {re.compile(regex): pre + sep for regex, pre in prefix.items()}
        else:
            raise TypeError(f'prefix argument in PrefixTransform must be either a str or '
                            f'dict. Received type "{type(prefix)}": {prefix}')
        self.quiet = quiet

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

        if type(self.prefix) is str:
            return self.prefix + record

        # If here, we've got a dict
        for regex, pre in self.prefix.items():
            if regex.search(record) is not None:
                return pre + record

        # If here, nothing matched
        if not self.quiet:
            logging.warning(f'PrefixTransform: no prefix pattern matched record "{record}"')
        return None