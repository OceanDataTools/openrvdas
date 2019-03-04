#!/usr/bin/env python3

import logging
import pprint
import sys
import time

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
    """Write record to table. Connectors assume we've got a DASRecord, but
    check; if we don't see if it's a suitably-formatted dict that we can
    convert into a DASRecord.
    """
    if type(record) is dict:
      try:
        data_id = record.get('data_id', 'no_data_id')
        timestamp = record.get('timestamp', None)
        fields = record['fields']
        record = DASRecord(data_id=data_id, timestamp=timestamp, fields=fields)
      except KeyError:
        logging.error('Unable to create DASRecord from dict:\n%s',
                      pprint.pformat(record))
    self.db.write_record(record)

  ############################
  def _delete_table(self,  table_name):
    """Delete a table."""
    self.db.delete_table(table_name)

  ############################
  def write(self, record):
    """Write out record, appending a newline at end. Connectors assume
    we've got a DASRecord, but check; if we don't see if it's a
    suitably-formatted dict that we can convert into a DASRecord.
    """
    if not record:
      return

    # If we've been passed a DASRecord, the field:value pairs are in a
    # field called, uh, 'fields'; if we've been passed a dict, it
    # could be either of the above formats. Try for the first, and if
    # it fails, assume the second.
    if type(record) is DASRecord:
      self._write_record(record)
      return
    
    if not type(record) is dict:
      logging.error('Record passed to CachedDataServer is not of type '
                    '"DASRecord" or dict; is type "%s"', type(record))
      return

    # If here, our record is a dict, figure out whether it is a top-level
    # field dict or not.
    data_id = record.get('data_id', None)
    timestamp = record.get('timestamp', time.time())

    # If we don't find a 'fields' entry in the dict, assume
    # (dangerously) that the entire record is a field dict.
    fields = record.get('fields', record)
    if not type(fields) is dict:
      logging.error('Fields of non-DASRecord passed to CachedDataServer are '
                    'not of type dict; type is "%s"', type(fields))
      return
      
    # Now figure out whether our fields are simple key:value pairs or
    #  key: [(timestamp, value), (timestamp, value),...] pairs.
    if not fields:
      logging.debug('Received empty fields in DatabaseWriter')
      return
    first_key = next(iter(fields))
    first_value = fields[first_key]
    if not type(first_value) is list:
      das_record = DASRecord(data_id=data_id, timestamp=timestamp,fields=fields)
      self._write_record(das_record)
      return

    # If here our we've got a field dict in which each field/key may
    # have multiple (timestamp, value) pairs. First thing we do is
    # reformat the data into a map of
    #        {timestamp: {field:value, field:value],...}}
    values_by_timestamp = {}
    try:
      for field, ts_value_list in fields.items():
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
