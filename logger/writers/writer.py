#!/usr/bin/env python3

import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402


class Writer:
    """
    Base class Writer about which we know nothing else. By default the
    input format is Unknown unless overridden.
    """
    ############################

    def __init__(self, input_format=formats.Unknown):
        """
        Abstract base class for data Writers.

        Concrete classes should implement the write(record) method and assign
        an input format that the writer accepts.

        A subclassed writer that accepts, e.g. text format records, should
        specify that in its init definition by, for example:
        ```
        class TextFileWriter(Writer):
          def __init__(self, filename):
            super().__init__(input_format=formats.Text)
            ...other things...
        ```
        The can_accept() method is intended to take an instance of a Reader or
        Transform - something that produces data and implements an
        output_format() method. To determine whether a writer can take input
        from a reader, call
        ```
          writer.can_accept(reader)
        ```
        The test will also return False if either the reader or writer have
        format specification of "Unknown".
        """
        self.input_format(input_format)

    ############################
    def input_format(self, new_format=None):
        """Return our input format, or set a new input format."""
        if new_format is not None:
            if not formats.is_format(new_format):
                raise TypeError('Argument %s is not a known format type', new_format)
            self.in_format = new_format
        return self.in_format

    ############################
    def can_accept(self, source):
        """Can we accept input from 'source'?"""
        # If source doesn't have an output_format() method, we don't know
        # whether or not we can accept its output, so return False
        output_format = getattr(source, 'output_format', None)
        if not callable(output_format):
            return False

        # Otherwise, check compatibility
        return self.input_format().can_accept(source.output_format())

    ############################
    def write(self, record):
        """Core method - write a record that we've been passed."""
        raise NotImplementedError('Class %s (subclass of Writer is missing '
                                  'implementation of write () method.'
                                  % self.__class__.__name__)

################################################################################


class TimestampedWriter(Writer):
    """
    A TimestampedWriter is a special case of a Writer where we
    can write out the timestamp associated with a record.
    """

    def __init__(self, input_format=formats.Unknown):
        super().__init__(input_format=input_format)
        pass

    def write_timestamp(self, record, timestamp=None):
        raise NotImplementedError('Abstract base class TimestampedWriter has no '
                                  'implementation of write_timestamp() method.')
