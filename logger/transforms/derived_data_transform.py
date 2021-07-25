#!/usr/bin/env python3

import sys
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class DerivedDataTransform(Transform):
    """Trivial base class for derived data transforms. Derived data
    transforms used to have some complicated invocation process to make
    them more efficient, but we've opted to make them just like any
    other transform for simplicity.
    """
    pass
