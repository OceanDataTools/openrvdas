#!/usr/bin/env python3
"""Write text records to a file. If no filename is specified, write to
stdout.

  writer = TextFileWriter(filename=None, flush=True, truncate=False)

      filename     Name of file to write to. If None, write to stdout

      flush        If True (default), flush after every write() call

      truncate     If True, truncate file before beginning to write


  writer.write(record)

                   Write out record, appending a newline at end  
"""

import sys
sys.path.append('.')

from utils.formats import Text
from writers.writer import Writer

################################################################################
# Write to the specified file. If filename is empty, write to stdout.
class TextFileWriter(Writer):
  def __init__(self, filename=None, flush=True, truncate=False):
    super().__init__(input_format=Text)

    if filename:
      if truncate:
        self.file = open(filename, 'w')
      else:
        self.file = open(filename, 'a')

    # If no filename specified, write to stdout
    else:
      self.file = sys.stdout
    self.flush = flush

  ############################
  def write(self, record):
    self.file.write(record + '\n')
    if self.flush:
      self.file.flush()
