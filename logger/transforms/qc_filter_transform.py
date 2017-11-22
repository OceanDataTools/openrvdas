#!/usr/bin/env python3
"""
TODO: option to initialize with a message to be output in case of failure.

TODO: option to intialize with a flag saying whether records will be
DASRecords or dictionary, or...?

"""

import logging
import sys

sys.path.append('.')

from logger.utils import formats
from logger.utils.das_record import DASRecord
from logger.transforms.transform import Transform

################################################################################
# 
class QCFilterTransform(Transform):
  """
  Transform that returns None unless values in passed DASRecord are out of
  bounds, in which case return a warning message."""
  def __init__(self, bounds, message=None):
    """
    bounds   A comma-separated list of conditions of the format

                <field_name>:<lower_bound>:<upper_bound>

             Either <lower_bound> or <upper_bound> may be empty.

    message  Optional string to be output instead of default when bounds
             are violated
    """
    super().__init__(input_format=formats.Python_Record,
                     output_format=formats.Text)

    self.message = message
    self.bounds = {}
    for condition in bounds.split(','):
      try:
        (var, lower_str, upper_str) = condition.split(':')
        lower = None if lower_str == '' else float(lower_str)
        upper = None if upper_str == '' else float(upper_str)
        self.bounds[var] = (lower, upper)
      except ValueError:
        raise ValueError('QCFilterTransform bounds must be colon-separated '
                         'triples of field_name:lower_bound:upper_bound. '
                         'Found "%s" instead.' % condition)

  ############################
  def transform(self, record):
    """Does record violate any bounds?"""
    if not record:
      return None

    errors = []

    if not type(record) is DASRecord:
      errors.append('Improper format record: %s' % str(record))

    else:
      for bound in self.bounds:
        if not bound in record.fields:
          continue
        value = record.fields.get(bound)
        (lower, upper) = self.bounds[bound]
        if type(value) is not int and type(value) is not float:
          errors.append('%s: non-numeric value: "%s"' % (bound, value))
          continue

        if lower is not None and value < lower:
          errors.append('%s: %g < lower bound %g' % (bound, value, lower))
        if upper is not None and value > upper:
          errors.append('%s: %g > upper bound %g' % (bound, value, upper))

    # If no errors, return None. Otherwise either return the specified
    # message (if we've been given one), or the joined string of
    # specific failures.
    if not errors:
      return None

    if self.message:
      return self.message
    else:
      return '; '.join(errors)

