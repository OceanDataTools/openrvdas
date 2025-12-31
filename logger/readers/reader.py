#!/usr/bin/env python3
"""
Abstract base class for data Readers.
"""

import sys
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.base_module import BaseModule   # noqa: E402


################################################################################
class Reader(BaseModule):
    """
    Base class Reader about which we know nothing else.

    Passes arguments quiet, encoding and encoding_errors up to BaseModule
    """
    ############################
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    ############################
    def read(self):
        """
        read() should return None when there are no more records.
        """
        raise NotImplementedError('Class %s (subclass of Reader) is missing '
                                  'implementation of read() method.'
                                  % self.__class__.__name__)

################################################################################


class StorageReader(Reader):
    """
    A StorageReader is something like a file, where we can, in theory,
    seek and rewind, or retrieve a range of records.
    """

    ############################
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    ############################
    # Behavior is intended to mimic file seek() behavior but with
    # respect to records: 'offset' means number of records, and origin
    # is either 'start', 'current' or 'end'.
    def seek(self, offset=0, origin='current'):
        raise NotImplementedError('Class %s (subclass of StorageReader) is missing '
                                  'implementation of seek() method.'
                                  % self.__class__.__name__)

    ############################
    def read_range(self, start=None, stop=None):
        """
        Read a range of records beginning with record number start, and ending
        *before* record number stop.
        """
        raise NotImplementedError('Class %s (subclass of StorageReader) is missing '
                                  'implementation of read_range() method.'
                                  % self.__class__.__name__)


################################################################################
class TimestampedReader(StorageReader):
    """
    A TimestampedReader is a special case of a StorageReader where we
    can seek and retrieve a range specified by timestamps.
    """

    ############################
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    ############################
    # Behavior is intended to mimic file seek() behavior but with
    # respect to timestamps: 'offset' means number of milliseconds, and
    # origin is either 'start', 'current' or 'end'.
    def seek_time(self, offset=0, origin='current'):
        raise NotImplementedError('Class %s (subclass of TimestampedReader) is missing '
                                  'implementation of seek_time() method.'
                                  % self.__class__.__name__)

    ############################
    # Read a range of records beginning with timestamp start
    # milliseconds, and ending *before* timestamp stop milliseconds.
    def read_time_range(self, start=None, stop=None):
        raise NotImplementedError('Class %s (subclass of TimestampedReader) is missing '
                                  'implementation of read_range() method.'
                                  % self.__class__.__name__)
