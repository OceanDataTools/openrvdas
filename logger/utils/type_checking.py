#!/usr/bin/env python3

import inspect
from typing import get_args


########################################
def get_method_type_hints(method):
    """
    When passed a method via something like

        get_method_type_hints(self.__class__.transform)

    return a dict of the method's type hints for the arguments
    and return value. E.g., if transform() is defined as:

        def transform(self, record: int|float) -> str:

    will return

        {'return': (<class 'str'>),
         'record': (<class 'int'>, <class 'float'>)}

    The point of this routine is to allow Transform and Writer to sanity
    check their inputs.
    """
    method_args = inspect.getfullargspec(method).annotations
    method_types = {k: tuple([value])
                    if isinstance(value, type)
                    else tuple(get_args(value))
                    for k, value in method_args.items()
                    }
    return method_types
