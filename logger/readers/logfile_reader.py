#!/usr/bin/env python3

import glob
import logging
import sys
import time

sys.path.append('.')

from logger.readers.reader import TimestampedReader
from logger.readers.text_file_reader import TextFileReader
from logger.utils.formats import Text
from logger.utils import timestamp

################################################################################
# Open and read single-line records from one or more text files.
class LogfileReader(TimestampedReader):
  """
  Read lines from one or more text files. Sequentially open all
  files that match the file_spec.
  """
  ############################
  def __init__(self, filebase=None, tail=False, refresh_file_spec=False,
               retry_interval=0.1, interval=0, use_timestamps=False,
               time_format=timestamp.TIME_FORMAT, start_time=None,
               end_time=None):
    """
    filebase     Possibly wildcarded string specifying files to be opened.
                 Special case: if file_spec is None, read from stdin.

    tail         If False, return None upon reaching end of last file; if
                 True, block upon reaching EOF of last file and wait for
                 more records.

    refresh_file_spec
                 If True, refresh the search for matching filenames when
                 reaching last EOF to see if any new matching files have
                 appeared in the interim.

    retry_interval
                 If tail and/or refresh_file_spec are True, how long to
                 wait before looking to see if any new records or files
                 have shown up.

    interval
                 How long to sleep between returning records. In general
                 this should be zero except for debugging purposes.

    use_timestamps
                 Return records in intervals that match their original
                 intervals.

    time_format
                 Format of the timestamps in the file(s).

    start_time
                 Skip records with a timestamp before this. Format must
                 match time_format.

    end_time
                 Skip records with a timestamp at or after this. Format must
                 match time_format.

    Note that the order in which files are opened will probably be in
    alphanumeric by filename, but this is not strictly enforced and
    depends on how glob returns them.
    """
    super().__init__(output_format=Text)

    if interval and use_timestamps:
      raise ValueError('Can not specify both "interval" and "use_timestamps"')

    self.filebase = filebase
    self.use_timestamps = use_timestamps
    self.time_format = time_format

    self.filter_by_time = start_time is not None or end_time is not None
    if self.filter_by_time:
      if start_time:
        self.start_timestamp = timestamp.timestamp(start_time,
                                                   time_format=time_format)
      else:
        self.start_timestamp = timestamp.MIN
      if end_time:
        self.end_timestamp = timestamp.timestamp(end_time,
                                                 time_format=time_format)
      else:
        self.end_timestamp = timestamp.MAX

    # If use_timestamps, we need to keep track of our last_read to
    # know how long to sleep
    self.last_timestamp = 0
    self.last_read = 0

    # If they give us a filebase, add wildcard to match its suffixes;
    # otherwise, we'll pass on the empty string to TextFileReader so
    # that it uses stdin. NOTE: we should really use a pattern that
    # echoes timestamp.DATE_FORMAT, e.g.
    # DATE_FORMAT_WILDCARD = '????-??-??'
    self.file_spec = filebase + '*' if filebase else None
    self.reader = TextFileReader(file_spec=self.file_spec,
                                 tail=tail,
                                 refresh_file_spec=refresh_file_spec,
                                 retry_interval=retry_interval,
                                 interval=interval)
    
  ############################
  def read(self):
    """
    Return the next line in the file(s), or None if there are no more
    records (as opposed to '' if the next record is a blank line). To test
    EOF you'll need to test

      if record is None:
        no more records...

    rather than simply

      if not record:
        could be EOF or simply an empty next line
    """
    record = self.reader.read()
    if not record:
      return None

    # NOTE: It feels like we should check here that the reader's
    # current file really does match our logfile name format...

    # If we're not time spacing or filtering records, we're done.
    if not self.use_timestamps and not self.filter_by_time:
      return record

    # Get timestamp off record
    time_str = record.split(' ', 1)[0]
    ts = timestamp.timestamp(time_str, time_format=self.time_format)

    if self.filter_by_time:
      # If record is not in desired time range, keep reading until one
      # is or until there are no more records.
      # Note: can't assume that records are in chronological order.
      while ts < self.start_timestamp or ts >= self.end_timestamp:
        record = self.reader.read()
        if not record:
          return None
        time_str = record.split(' ', 1)[0]
        ts = timestamp.timestamp(time_str, time_format=self.time_format)

    # If we're not trying to return records in intervals that match
    # their original intervals, we're done - just return it.
    if not self.use_timestamps:
      return record

    desired_interval = ts - self.last_timestamp
    now = timestamp.timestamp()
    actual_interval = now - self.last_read
    logging.debug('Desired interval %f, actual %f; sleeping %f',
                  desired_interval, actual_interval,
                  max(0, desired_interval-actual_interval))
    time.sleep(max(0, desired_interval - actual_interval))

    self.last_timestamp = ts
    self.last_read = timestamp.timestamp()

    return record

