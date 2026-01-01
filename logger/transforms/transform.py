#!/usr/bin/env python3
"""
The biggest thing that the abstract parent class Transform now does is help
with (optional) type checking of the child class' inputs. In the past, an
explicit, but very awkward, form of type checking was used, with child classes
passing the Transform class a list of input_format and output_format specifications.

That is now deprecated in favor of using Python's type hints. Type hints should be
specified for the child class' transform() method. Then the transform() method can
call self.can_process_record(record) to see whether it's one of the input types it
can handle. If not, it can "return self.digest_record(record) to have the parent
class try to deal with it:

E.g.:
     def transform(self, record: Union[int, str, float]):
        if not self.can_process_record(record):  # inherited from BaseModule()
            return self.digest_record(record)  # inherited from BaseModule()
         return str(record) + '+'

If no type hints are specified, can_process_record() will return True for all
records *except* those of type "None" or "list". The logic is that digest_record()
will return a None when given a None, and when given a list, will iteratively
apply the transform to every element of the list and return the resulting list.

Note that the child class can explicitly call super().__init__() or such
to initialize the type checking and set its debugging level. If it is not explicitly
initialized, it will be done implicitly the first time can_process_record() or
digest_record() are called, but with the default of quiet=False.
"""
import sys
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.base_module import BaseModule  # noqa: E402


################################################################################
class Transform(BaseModule):
    """
    Base class Transform about which we know nothing else.

    Passes arguments quiet, encoding and encoding_errors up to BaseModule
    """
    ############################
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._initialize_type_hints()

    ############################
    def _initialize_type_hints(self):
        """ Retrieve any type hints for child transform() method so we can
        check whether the type of record we've received can be parsed
        natively or not."""
        super()._initialize_type_hints(module_type='transform',
                                       module_method=self.__class__.transform)
