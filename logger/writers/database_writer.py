#!/usr/bin/env python3

import logging
import sys

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.formats import Python_Record
from logger.utils.das_record import DASRecord
from logger.writers.writer import Writer

# Don't freak out if we can't find database settings - unless they actually
# try to instantiate a DatabaseWriter.
try:
  from database.settings import DATABASE_ENABLED, Connector
  from database.settings import DEFAULT_DATABASE, DEFAULT_DATABASE_HOST
  from database.settings import DEFAULT_DATABASE_USER, DEFAULT_DATABASE_PASSWORD
  DATABASE_SETTINGS_FOUND = True
except ModuleNotFoundError:
  DATABASE_SETTINGS_FOUND = False
  DEFAULT_DATABASE = DEFAULT_DATABASE_HOST = None
  DEFAULT_DATABASE_USER = DEFAULT_DATABASE_PASSWORD = None

################################################################################
class DatabaseWriter(Writer):
  def __init__(self, database=DEFAULT_DATABASE, host=DEFAULT_DATABASE_HOST,
               user=DEFAULT_DATABASE_USER, password=DEFAULT_DATABASE_PASSWORD,
               field_dict_input=False):
    """Write to the passed DASRecord to a database table.

    If flag field_dict_input is true, expect input in the format

       {field_name: [(timestamp, value), (timestamp, value),...],
        field_name: [(timestamp, value), (timestamp, value),...],
        ...
       }

    Otherwise expect input to be a DASRecord."""
    super().__init__(input_format=Python_Record)

    if not DATABASE_SETTINGS_FOUND:
      raise RuntimeError('File database/settings.py not found. Database '
                         'functionality is not available. Have you copied '
                         'over database/settings.py.dist to settings.py?')
    if not DATABASE_ENABLED:
      raise RuntimeError('Database not configured in database/settings.py; '
                         'DatabaseWriter unavailable.')

    self.db = Connector(database=database, host=host,
                        user=user, password=password)
    self.field_dict_input = field_dict_input

  ############################
  def _table_exists(self, table_name):
    """Does the specified table exist in the database?"""
    return self.db.table_exists(table_name)

  ############################
  def _write_record(self, record):
    """Write record to table."""
    self.db.write_record(record)

  ############################
  def _delete_table(self,  table_name):
    """Delete a table."""
    self.db.delete_table(table_name)

  ############################
  def write(self, record):
    """ Write out record, appending a newline at end."""
    if not record:
      return

    # If input purports to not be a field dict, it should be a
    # DASRecord. Just write it out.
    if not self.field_dict_input:
      if type(record) is DASRecord:
        self._write_record(record)
      else:
        logging.error('Record passed to DatabaseWriter is not of type '
                      '"DASRecord"; is type "%s"', type(record))
      return

    # If here, we believe we've received a field dict, in which each
    # field may have multiple [timestamp, value] pairs. First thing we
    # do is reformat the data into a map of
    #        {timestamp: {field:value, field:value],...}}
    if not type(record) is dict:
      raise ValueError('DatabaseWriter.write() received record purporting '
                         'to be a field dict but of type %s' % type(record))
    values_by_timestamp = {}
    try:
      for field, ts_value_list in record.items():
        for (timestamp, value) in ts_value_list:
          if not timestamp in values_by_timestamp:
            values_by_timestamp[timestamp] = {}
          values_by_timestamp[timestamp][field] = value
    except ValueError:
      logging.error('Badly-structured field dictionary: %s: %s',
                    field, pprint.pformat(ts_value_list))

    # Now go through each timestamp, generate a DASRecord from its
    # values, and write them.
    for timestamp in sorted(values_by_timestamp):
      das_record = DASRecord(timestamp=timestamp,
                             fields=values_by_timestamp[timestamp])
      self._write_record(das_record)
