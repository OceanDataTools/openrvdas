#!/usr/bin/env python3
"""
The biggest thing that the abstract parent class Writer now does is help
with (optional) type checking of the child class' inputs. In the past, an
explicit, but very awkward, form of type checking was used, with child classes
passing the Transform class a list of input_format and output_format specifications.

That is now deprecated in favor of using Python's type hints. Type hints should be
specified for the child class' write() method. Then the write() method can
call self.can_process_record(record) to see whether it's one of the input types it
can handle. If not, it can "return self.digest_record(record) to have the parent
class try to deal with it:

E.g.:
     def write(self, record: Union[int, str, float]):
        if not self.can_process_record(record):  # inherited from BaseModule()
            self.digest_record(record)           # inherited from BaseModule()
            return
        [do normal writing here...

If no type hints are specified, can_process_record() will return True for all
records *except* those of type "None" or "list". The logic is that digest_record()
will return a None when given a None, and when given a list, will iteratively
apply the write() to every element of the list in order.

Note that the child class can explicitly call super().__init__(quiet=True) or such
to initialize the type checking and set its debugging level. If it is not explicitly
initialized, it will be done implicitly the first time can_process_record() or
digest_record() are called, but with the default of quiet=False.
"""
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.base_module import BaseModule  # noqa: E402


class Writer(BaseModule):
    """
    Base class Writer about which we know nothing else. By default the
    input format is Unknown unless overridden.

    Passes arguments quiet, encoding and encoding_errors up to BaseModule
    """
    ############################

    def __init__(self, **kwargs):
        """Abstract base class for data Writers.
        """
        super().__init__(**kwargs)
        self._initialize_type_hints()

    ############################
    def _initialize_type_hints(self):
        """ Retrieve any type hints for child write() method so we can
        check whether the type of record we've received can be parsed
        natively or not."""
        super()._initialize_type_hints(module_type='write',
                                       module_method=self.__class__.write)

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

    ############################
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    ############################
    def write_timestamp(self, record, timestamp=None):
        raise NotImplementedError('Abstract base class TimestampedWriter has no '
                                  'implementation of write_timestamp() method.')
