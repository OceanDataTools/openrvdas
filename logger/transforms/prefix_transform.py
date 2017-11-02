#!/usr/bin/env python3
"""Prepend a prefix to a text record.
"""

import sys
sys.path.append('.')

from logger.utils import formats

from logger.transforms.transform import Transform

################################################################################
# If timestamp_format is not specified, use default format
class PrefixTransform(Transform):
  def __init__(self, prefix, sep=' '):
    super().__init__(input_format=formats.Text, output_format=formats.Text)
    self.prefix = prefix + sep

  # Prepend a prefix
  def transform(self, record):
    if record is None:
      return None
    return self.prefix + record
