#!/usr/bin/env python3

import sys
sys.path.append('.')

from logger.utils.formats import Text
from logger.writers.writer import Writer

################################################################################
class TextFileWriter(Writer):
  """Write to the specified file. If filename is empty, write to stdout."""
  def __init__(self, filename=None, flush=True, truncate=False):
    """
    Write text records to a file. If no filename is specified, write to
    stdout.

    filename     Name of file to write to. If None, write to stdout

    flush        If True (default), flush after every write() call

    truncate     If True, truncate file before beginning to write
    """
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
    """ Write out record, appending a newline at end."""
    if record is not None:
      self.file.write(record + '\n')
    if self.flush:
      self.file.flush()
