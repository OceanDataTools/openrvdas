#!/usr/bin/env python3
"""Abstract base class for data Transforms.

Note that when a Transform is first instantiated, it may not yet know
what its inputs are going to be, so we provide methods to override the
input/output formats after the fact.

"""

import sys
sys.path.append('.')

from utils import formats

################################################################################
# Base class Transform about which we know nothing else. By default the
# input and output formats are Unknown unless overridden.
class Transform:
  def __init__(self, input_format=formats.Unknown,
               output_format=formats.Unknown):
    self.input_format(input_format)
    self.output_format(output_format)

  # Return our input format, or set a new input format
  def input_format(self, new_format=None):
    if new_format is not None:
      if not formats.is_format(new_format):
        raise TypeError('Argument %s is not a known format type', new_format)
      self.in_format = new_format
    return self.in_format

  # Return our output format or set a new output format
  def output_format(self, new_format=None):
    if new_format is not None:
      if not formats.is_format(new_format):
        raise TypeError('Argument %s is not a known format type', new_format)
      self.out_format = new_format
    return self.out_format

  # transform() should return None if the result of its transformation
  # is an empty record.
  def transform(self, record):
    raise NotImplementedError('Class %s (subclass of Transform) is missing '
                              'implementation of transform() method.'
                              % self.__class__.__name__)
