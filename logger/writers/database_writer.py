#!/usr/bin/env python3

import logging
import sys

sys.path.append('.')

from logger.utils.formats import Python_Record
from logger.utils.das_record import DASRecord
from logger.writers.writer import Writer

from database.settings import DATABASE_ENABLED, Connector
from database.settings import DEFAULT_DATABASE, DEFAULT_DATABASE_HOST
from database.settings import DEFAULT_DATABASE_USER, DEFAULT_DATABASE_PASSWORD

################################################################################
class DatabaseWriter(Writer):
  def __init__(self, database=DEFAULT_DATABASE, host=DEFAULT_DATABASE_HOST,
               user=DEFAULT_DATABASE_USER, password=DEFAULT_DATABASE_PASSWORD,
               skip_record_type_check=False):
    """Write to the passed DASRecord to a database table."""
    super().__init__(input_format=Python_Record)

    if not DATABASE_ENABLED:
      raise RuntimeError('Database not configured; DatabaseWriter unavailable.')

    self.db = Connector(database=database, host=host,
                        user=user, password=password)
    self.skip_record_type_check = skip_record_type_check

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

    # By default, check that what we've got is a DASRecord
    if not self.skip_record_type_check and type(record) is not DASRecord:
      logging.error('Record passed to DatabaseWriter is not of type '
                    '"DASRecord"; is type "%s"', type(record))
      return

    # Write the record
    self._write_record(record)
