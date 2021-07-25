#!/usr/bin/env python3
"""Slice fields out of the specified text record."""

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class SliceTransform(Transform):
    def __init__(self, fields=None, sep=None):
        """
        ```
        fields    A comma-separated list of integers and/or ranges. A range
                  is an int:int pair, where either or both of the ints may
                  be omitted to mean the extreme values (0 or sys.maxsize).

        sep       Field separator; if omitted, uses default behavior of split()
                  which assumes all contiguous whitespace as a single separator.
        ```
        Example:
        ```
          transform = SliceTransform(':3,5:7,9,11:')

          record = transform.transform('a b c d e f g h i j k l')
        ```
        should yield ``'a b c f g j l'``.

        Note that Python slice indexing applies, so '-3:-1' is a valid spec.
        Note also that there's nothing requiring that fields are in order,
        non-overlapping and/or non-repeating. The following definition is just
        fine.
        ```
        transform = SliceTransform('9,0,4,0,0:2')
        ```
        """
        super().__init__(input_format=formats.Text, output_format=formats.Text)
        if not fields:
            fields = ':'

        self.fields = []
        self.sep = sep
        try:
            for field in fields.split(','):
                logging.debug('SliceTransform parsing field "%s"', field)
                # If field spec is a range, num:num, store as tuple of ints
                if field.find(':') > -1:
                    (start, end) = field.split(':')
                    if start == '':  # if missing start, e.g.   ':5'
                        start = 0
                    if end == '':    # if missing end, e.g.   '1:'
                        end = sys.maxsize
                    self.fields.append((int(start), int(end)))

                    # If field is a simple number
                else:
                    self.fields.append(int(field))
        except ValueError as e:
            logging.error('Bad field format "%s" - %s', field, e)
            raise e

    ############################
    def transform(self, record):
        """Strip and return only the requested fields."""
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

        if not type(record) is str:
            logging.warning('SliceTransform received non-string input: %s', record)
            return None

        in_record = record.split(self.sep)
        out_record = []
        for field in self.fields:
            if type(field) is tuple:
                slice = in_record[field[0]:field[1]]
            else:
                slice = [in_record[field]]

            logging.debug('SliceTransform.write() selecting %s: %s', field, slice)
            out_record.extend(slice)
        separator = self.sep or ' '
        return separator.join(out_record)
