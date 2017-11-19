#!/usr/bin/env python3
"""Return None unless values in passed DASRecord are out of bounds, in
which case return a warning message.

  transform = QCFilterTransform(bounds)

where bounds is a comma-separated list of conditions of the format

  <field_name>:<lower_bound>:<upper_bound>

Either <lower_bound> or <upper_bound> may be empty.

Transform formats:
  input_format:  Python_Record
  output_format: Text

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
  def __init__(self, bounds):
    super().__init__(input_format=formats.Python_Record,
                     output_format=formats.Text)

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
  # Does record violate any bounds?
  def transform(self, record):
    if not record:
      return None

    if not type(record) is DASRecord:
      return('Improper format record: %s' % str(record))

    errors = []
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

    # If we've had any errors; append them into a string and return
    if errors:
      return '; '.join(errors)
    return None
