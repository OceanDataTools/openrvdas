#!/usr/bin/env python3
"""
The biggest thing that the abstract parent class Transform now does is help
with (optional) type checking of the child class' inputs. In the past, an
explicit, but very awkward, form of type checking was used, with child classes
passing the Transform class a list of input_format and output_format specifications.

This is now deprecated in favor of using Python's type hints. Type hints should be
specified for the child class' transform() method. Then the transform() method can
call self.can_process_record(record) to see whether it's one of the input types it
can handle. If not, it can "return self.digest_record(record) to have the parent
class try to deal with it:

E.g.:
     def transform(self, record: Union[int, str, float]):
        if not self.can_process_record(record):  # inherited from Transform()
            return self.digest_record(record)  # inherited from Transform()
         return str(record) + '+'

If no type hints are specified, can_process_record() will return True for all
records *except* those of type "None" or "list". The logic is that digest_record()
will return a None when given a None, and when given a list, will iteratively
apply the transform to every element of the list and return the resulting list.
"""
import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.type_checking import get_method_type_hints  # noqa: E402


################################################################################
class Transform:
    """
    Base class Transform about which we know nothing else.

    Implements method for checking whether a received record is in a format
    that the derived class can process, and also a method for splitting a
    list of records into its elements and calling subclass transform() on them.
    """
    ############################
    def __init__(self, quiet=False, input_format=None, output_format=None):
        self.quiet = quiet
        self._initialize_type_hints(quiet=quiet)

        if input_format or output_format:
            logging.warning(f'Code warning: {self.__class__.__name__} use of '
                            f'"input_format" or "output_format" is deprecated. '
                            f'Please see Transform code documentation.')

    ############################
    def _initialize_type_hints(self, quiet=False):
        """ Retrieve any type hints for child transform() method so we can
        check whether the type of record we've received can be parsed
        natively or not."""
        transform_type_hints = get_method_type_hints(self.__class__.transform)
        self.input_types = transform_type_hints.get('record')
        self.return_types = transform_type_hints.get('return')

        # logging.warning(f'input_types: {self.input_types}')
        # logging.warning(f'return_types: {self.return_types}')

        # Other things we'd want to make sure are defined.
        self.quiet = quiet
        self.class_name = self.__class__.__name__
        self.initialized = True

    ############################
    def can_process_record(self, record):
        """ Is this record in a format that the transform can handle?

        - If there are type hints: True if type of record is in type hints.
        - If there are no type hints: False if None or list, otherwise True.

        The logic is that if there are no type hints and we see False or
        a list, we expect digest_record() to be called to deal with it."""

        try:  # if we've not been initialized with type hints, initialize now
            self.initialized or True
        except AttributeError:
            self._initialize_type_hints()

        if self.input_types:
            return isinstance(record, self.input_types)

        # If not type hints, make some judgment calls. Say "no" to None
        # and to lists, because we'll expect that answer to trigger a
        # call to digest_record(), which will handle them.
        if record is None or isinstance(record, list):
            return False
        return True

    ############################
    def digest_record(self, record):
        """ Try to digest record down into a format that the transform can
        handle. Typically that will mean that we've been handed a list of
        records that we need to break into individual records."""

        try:  # if we've not been initialized with type hints, initialize now
            self.initialized or True
        except AttributeError:
            self._initialize_type_hints()

        if record is None:
            return None

        # If it's a type the transform can handle directly (though, if so,
        # why were we called?!?
        if self.can_process_record(record) and not self.quiet:
            logging.warning(f'{self.class_name}: digest_record() called unnecessarily.')
            logging.warning(f'Can process {self.input_types}; received {type(record)}: {record}')
            return self.transform(record)

        # We know how to deal with it if it's a list: Apply to components,
        # stripping out any None's
        if isinstance(record, list):
            result = [self.transform(r) for r in record if r is not None]
            return [r for r in result if r is not None]  # remove Nones

        # If we don't know how to deal with it
        if not self.quiet:
            logging.warning(f'Unable to convert record to format "{self.class_name}" can process')
            logging.warning(f'Must be instance or list of {self.input_types}')
            logging.warning(f'Received {type(record)}: {record}')
        return None
