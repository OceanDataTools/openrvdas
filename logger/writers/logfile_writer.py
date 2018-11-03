#!/usr/bin/env python3

import logging
import sys
sys.path.append('.')

from logger.utils import timestamp
from logger.utils.formats import Text
from logger.writers.writer import Writer
from logger.writers.text_file_writer import TextFileWriter

################################################################################
class LogfileWriter(Writer):
  """Write to the specified file. If filename is empty, write to stdout."""
  def __init__(self, filebase=None, flush=True,
               time_format=timestamp.TIME_FORMAT,
               date_format=timestamp.DATE_FORMAT):
    """
    Write timestamped text records to file. Base filename will have
    date appended, in keeping with R2R format recommendations
    (http://www.rvdata.us/operators/directory). When timestamped date on
    records rolls over to next day, create new file with new date suffix.

    filebase     Base name of file to write to. Will have record date
                 appended, e.g.

    flush        If True (default), flush after every write() call

    date_fomat   A strftime-compatible string, such as '%Y-%m-%d'; defaults
                 to whatever's defined in utils.timestamps.DATE_FORMAT.
    """
    super().__init__(input_format=Text)

    self.filebase = filebase
    self.flush = flush
    self.time_format = time_format
    self.date_format = date_format

    self.current_date = None
    self.current_filename = None
    self.writer = None

  ############################
  def write(self, record):
    """Note: Assume record begins with a timestamp string."""
    if record is None:
      return

    # First things first: get the date string from the record
    try:
      time_str = record.split()[0]
      ts = timestamp.timestamp(time_str, time_format=self.time_format)
      date_str = timestamp.date_str(ts, date_format=self.date_format)
      logging.debug('LogfileWriter date_str: %s', date_str)
    except ValueError:
      logging.error('LogfileWriter.write() - bad record timestamp: %s', record)
      return

    # Is it time to create a new file to write to?
    if not self.writer or date_str != self.current_date:
      self.current_filename = self.filebase + '-' + date_str
      self.current_date = date_str
      logging.info('LogfileWriter opening new file: %s', self.current_filename)
      self.writer = TextFileWriter(self.current_filename, self.flush)

    logging.debug('LogfileWriter writing record: %s', record)
    self.writer.write(record)
