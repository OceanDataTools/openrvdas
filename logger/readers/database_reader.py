#!/usr/bin/env python3

import logging
import socket
import sys
import time

sys.path.append('.')

from logger.utils.formats import Python_Record
from logger.utils.das_record import DASRecord
from logger.readers.reader import TimestampedReader

from database.settings import DATABASE_ENABLED, Connector

################################################################################
# Read to the specified file. If filename is empty, read to stdout.
class DatabaseReader(TimestampedReader):
  """
  Database records to DASRecords.
  """
  ############################
  def __init__(self, database, host, user, password,
               data_id, message_type=None, sleep_interval=2):
    super().__init__(output_format=Python_Record)

    if not DATABASE_ENABLED:
      raise RuntimeError('Database not configured; DatabaseReader unavailable.')

    self.db = Connector(database=database, host=host,
                        user=user, password=password)
    dummy_das_record = DASRecord(data_id=data_id, message_type=message_type)
    self.table_name = self.db.table_name(dummy_das_record)
    self.sleep_interval = sleep_interval
    self.next_id = 1

    if not self.db.table_exists(self.table_name):
      logging.info('Database table "%s" (for data_id "%s", message_type '
                      '"%s") does not exist (yet)', self.table_name,
                      data_id, message_type)

  ############################
  def read_range(self, start=None, stop=None):
    """Read all records beginning at record number 'stop' and ending
    *before* record number 'stop'."""
    if not self.db.table_exists(self.table_name):
      return None

    if stop is not None:
      num_records = stop - start;
    else:
      num_rec
    return self.db.read_range(self.table_name, start, stop)

  ############################
  def read_time_range(self, start_time=None, stop_time=None):
    """Read all records within specified time range. If start_time is
    None, read from first available record. If stop_time is None, read
    up to last available record."""
    if not self.db.table_exists(self.table_name):
      return None

    return self.db.read_time_range(self.table_name, start_time, stop_time)

  ############################
  def read(self):
    """
    Read next record in table. Sleep and retry if there's no new record to read.
    """
    while not self.db.table_exists(self.table_name):
      logging.info('read() called on non-existent table "%s"; sleeping',
                   self.table_name)
      time.sleep(self.sleep_interval)

    while True:
      record = self.db.read(self.table_name)
      if record:
        return record
      logging.debug('No new record returned by database read. Sleeping')
      time.sleep(self.sleep_interval)
