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
from database.settings import DEFAULT_DATABASE, DEFAULT_DATABASE_HOST
from database.settings import DEFAULT_DATABASE_USER, DEFAULT_DATABASE_PASSWORD

################################################################################
# Read records from specified table.
class DatabaseReader(TimestampedReader):
  """
  Database records to DASRecords.
  """
  ############################
  def __init__(self, data_id, message_type=None,
               database=DEFAULT_DATABASE, host=DEFAULT_DATABASE_HOST,
               user=DEFAULT_DATABASE_USER, password=DEFAULT_DATABASE_PASSWORD,
               sleep_interval=2):
    super().__init__(output_format=Python_Record)

    if not DATABASE_ENABLED:
      raise RuntimeError('Database not configured; DatabaseReader unavailable.')

    self.db = Connector(database=database, host=host,
                        user=user, password=password)

    dummy_das_record = DASRecord(data_id=data_id, message_type=message_type)
    self.table_name = self.db.table_name_from_record(dummy_das_record)
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
    return self.db.read_range(self.table_name, start=start, stop=stop)

  ############################
  def read_time_range(self, start_time=None, stop_time=None):
    """Read all records within specified time range. If start_time is
    None, read from first available record. If stop_time is None, read
    up to last available record."""
    if not self.db.table_exists(self.table_name):
      return None

    return self.db.read_time_range(self.table_name, start_time=start_time,
                                   stop_time=stop_time)

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

################################################################################
# Read specific fields from database.
class DatabaseFieldReader(TimestampedReader):
  """
  Timestamped database fields to dictionary.
  """
  ############################
  def __init__(self, fields,
               database=DEFAULT_DATABASE, host=DEFAULT_DATABASE_HOST,
               user=DEFAULT_DATABASE_USER, password=DEFAULT_DATABASE_PASSWORD,
               sleep_interval=2):
    super().__init__()

    if not DATABASE_ENABLED:
      raise RuntimeError('Database not configured; DatabaseReader unavailable.')

    self.db = Connector(database=database, host=host,
                        user=user, password=password)

    self.fields = fields
    logging.info('Created DatabaseFieldReader for %s', fields)

    # Map from field names to table names and back. Keep track if we have
    # a table for every field or not.
    self.field_to_table = {}
    self.table_to_field = {}  # value is list of fields in each table
    self.map_is_complete = False

    self.sleep_interval = sleep_interval
    self.last_timestamp = 0

  ############################
  # Figure out which table corresponds to each field. Return True if
  # all fields have tables and we have a complete mapping.
  def _build_field_map(self):
    map_is_complete = True
    for field in self.fields:
      if field in self.field_to_table:
        continue
      
      # Field's table isn't in our cache; try looking up from db.
      table = self.db.table_name_from_field(field)
      if not table:
        map_is_complete = False
        continue

      # We've found table. Cache it.
      self.field_to_table[field] = table
      if not table in self.table_to_field:
        self.table_to_field[table] = []
      self.table_to_field[table].append(field)

    # Map is complete if we've found tables for all fields
    return map_is_complete

  ############################
  def read_range(self, start=None, stop=None):
    """NOT IMPLEMENTED - not a well-defined concept for DatabaseFieldReader."""
    raise NotImplementedError('Method read_range() not defined for '
                              'DatabaseFieldReader - it doesn\'t make sense.')

  ############################
  def read_time_range(self, start_time=None, stop_time=None):
    """Read all records within specified time range. If start_time is
    None, read from first available record. If stop_time is None, read
    up to last available record."""

    # If we don't yet have mappings for all the specified fields, see if
    # any of the still missing tables have now shown up.
    if not self.map_is_complete:
      self.map_is_complete = self._build_field_map()

    result = {}
    for table_name, field_list in self.table_to_field.items():
      records = self.db.read_time_range(table_name=table_name,
                                        field_list=field_list,
                                        start_time=start_time,
                                        stop_time=stop_time)
      # If we got a record, append its timestamp and field values
      # into result.
      for record in records:
        for field, value in record.fields.items():
          if not field in result:
            result[field] = []
          result[field].append((record.timestamp, value))
    return result
  
  ############################
  def read(self):
    """Read next record in table. Sleep and retry if there's no new record
    to read."""
    # If we don't yet have mappings for all the specified fields, see if
    # any of the still missing tables have now shown up.
    if not self.map_is_complete:
      self.map_is_complete = self._build_field_map()

    while True:
      result = {}
      for table_name, field_list in self.table_to_field.items():
        record = self.db.read(table_name=table_name, field_list=field_list)
        if not record:
          continue

        # If we got a record, append its timestamp and field values
        # into result.
        for field, value in record.fields.items():
          if not field in result:
            result[field] = []
          result[field].append((record.timestamp, value))

      if result:
        return result

      logging.debug('No new record returned by database read. Sleeping')
      time.sleep(self.sleep_interval)
