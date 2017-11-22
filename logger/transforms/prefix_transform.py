#!/usr/bin/env python3

import sys
sys.path.append('.')

from logger.utils import formats
from logger.transforms.transform import Transform

################################################################################
class PrefixTransform(Transform):
  """Prepend a prefix to a text record."""
  def __init__(self, prefix, sep=' '):
    """Use space as default separator."""
    super().__init__(input_format=formats.Text, output_format=formats.Text)
    self.prefix = prefix + sep

  ############################
  def transform(self, record):
    """Prepend a prefix."""
    if record is None:
      return None
    return self.prefix + record
