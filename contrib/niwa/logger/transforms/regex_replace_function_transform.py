#!/usr/bin/env python3

import re
import sys
import math

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class RegexReplaceFunctionTransform(Transform):
    """Apply regex replacements to record using a function. See test_regex_replace_function for example usage"""
    ############################

    def __init__(self, patterns, count=0, flags=0):
        """
        patterns - a dict of {pattern:fn, pattern:fn} to be matched and replaced.
                   Note that replacement order is not guaranteed.
        """
        super().__init__(input_format=formats.Text, output_format=formats.Text)

        self.patterns = patterns
        self.count = count
        self.flags = flags

    ############################
    def transform(self, record):
        """Does record contain pattern?"""
        if not record:
            return None

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list.
        if type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record))
            return results

        # Apply all patterns in order
        result = record
        for old_str, new_str in self.patterns.items():
            # escape backslashes added by conversion to json and back
            old_str = old_str.encode('latin-1', 'backslashreplace').decode('unicode-escape')
            matches = re.findall(old_str, result)

            for match in matches:
                # other libraries can be made available to the functions by adding to the dict here
                new_value = str(eval(new_str, {"math": math, "match": match}))
                result = re.sub(old_str, new_value, result, self.count, self.flags)

        return result
