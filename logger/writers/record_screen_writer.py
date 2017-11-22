#!/usr/bin/env python3

import logging
import shutil
import sys

sys.path.append('.')

from logger.utils.formats import Python_Record
from logger.utils.das_record import DASRecord
from logger.writers.writer import Writer

################################################################################
class RecordScreenWriter(Writer):
  """Write DASRecords to terminal screen in some survivable
  format. Mostly intended for debugging."""
  def __init__(self):
    super().__init__(input_format=Python_Record)

    self.values = {}
    self.timestamps = {}
    self.latest = 0

  ############################
  def move_cursor(self, x, y):
    print('\033[{};{}f'.format(str(x), str(y)))
    
  ############################
  # receives a DASRecord
  def write(self, record):
    if not record:
      return
    if not type(record) is DASRecord:
      logging.error('ScreenWriter got non-DASRecord: %s', str(type(record)))
      return

    # Incorporate the values from the record
    self.latest = record.timestamp
    for field in record.fields:
      self.values[field] = record.fields[field]
      self.timestamps[field] = self.latest

    # Get term size, in case it's been resized
    (cols, rows) = shutil.get_terminal_size()
    self.move_cursor(0,0)    
    # Redraw stuff
    keys =  sorted(self.values.keys())
    for i in range(rows):
      # Go through keys in alpha order
      if i < len(keys):
        key = keys[i]
        line = '{} : {}'.format(key, self.values[key])

      # Fill the rest of the screen with blank lines
      else:
        line = ''

      # Pad the lines out to screen width to overwrite old stuff
      pad_size = cols - len(line)
      line += ' ' * pad_size
      
      print(line)

