#!/usr/bin/env python3

import re
import sys

sys.path.append('.')

from logger.utils import formats
from logger.transforms.transform import Transform

################################################################################
class RegexFilterTransform(Transform):
  """Only return records matching the specified regular expression."""
  ############################
  def __init__(self, pattern, flags=0, negate=False):
    """If negate=True, only return records that *don't* match the pattern."""
    super().__init__(input_format=formats.Text, output_format=formats.Text)
    self.pattern = re.compile(pattern, flags)
    self.negate = negate

  ############################
  def transform(self, record):
    """Does record contain pattern?"""
    if not record:
      return None

    match = self.pattern.search(record)
    if match is None:
      if self.negate:
        return record
      return None
    else:
      if self.negate:
        return None
      return record
