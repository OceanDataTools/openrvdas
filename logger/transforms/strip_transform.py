#!/usr/bin/env python3
"""Strip undesired characters out of a record."""

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class StripTransform(Transform):
    def __init__(self, chars=None, unprintable=False,
                 strip_prefix=False, strip_suffix=False, **kwargs):
        """
        ```
        chars     A string of characters that are to be stripped out of the
                  record. By default, the transform will remove them regardless
                  of where in the record they occur. If omitted, will strip standard
                  whitespace characters.

        unprintable - As an alternative to specifying 'chars', setting unprintable
                  to True will strip out all unprintable characters.

        strip_prefix - If true, strip characters at the start of the record,
                  rather than everywhere (compatible with strip_suffix).

        strip_suffix - If true, strip characters at the end of the record,
                  rather than everywhere (compatible with strip_prefix).
        ```
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        if chars and unprintable:
            raise ValueError('Can not specify both "chars" and "unprintable".')
        self.chars = chars or ' \t\v\r\n\f'
        self.unprintable = unprintable
        self.strip_prefix = strip_prefix
        self.strip_suffix = strip_suffix

    ############################
    def transform(self, record: str) -> str:
        """Strip and return only the requested fields."""

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            return self.digest_record(record)  # inherited from BaseModule()

        if not type(record) is str:
            logging.warning('SplitTransform received non-string input: %s', record)
            return None

        # If we're stripping unprintables
        if self.unprintable:
            if not self.strip_prefix and not self.strip_suffix:
                record = ''.join([c for c in record if c.isprintable()])
            if self.strip_prefix:
                while record and not record[0].isprintable():
                    record = record[1:]
            if self.strip_suffix:
                while record and not record[-1].isprintable():
                    record = record[:-1]

        # If we're working with a specified character set
        else:
            if not self.strip_prefix and not self.strip_suffix:
                record = ''.join([c for c in record if c not in self.chars])
            if self.strip_prefix:
                record = record.lstrip(self.chars)
            if self.strip_suffix:
                record = record.rstrip(self.chars)

        return record
