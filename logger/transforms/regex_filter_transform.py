#!/usr/bin/env python3
"""Only return records matching the specified regular expression. If
negate=True, only return records that *don't* match the pattern.
"""

import re
import sys

sys.path.append('.')

from logger.utils import formats

from logger.transforms.transform import Transform

################################################################################
# 
class RegexFilterTransform(Transform):
  def __init__(self, pattern, flags=0, negate=False):
    super().__init__(input_format=formats.Text, output_format=formats.Text)
    self.pattern = re.compile(pattern, flags)
    self.negate = negate

  # Does record contain pattern?
  def transform(self, record):
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
