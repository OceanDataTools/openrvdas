#!/usr/bin/env python3

import logging
import sys

sys.path.append('.')
  
from logger.utils.formats import Python_Record
from logger.utils.das_record import DASRecord
from logger.writers.writer import Writer

from database.settings import DATABASE_ENABLED, Connector

################################################################################
class DatabaseWriter(Writer):
  def __init__(self, database, host, user, password,
               create_if_missing=False, skip_record_type_check=False):
    """Write to the passed DASRecord to a database table. If
    create_if_missing is true, create the table if it doesn't yet
    exist."""
    super().__init__(input_format=Python_Record)

    if not DATABASE_ENABLED:
      raise RuntimeError('Database not configured; DatabaseWriter unavailable.')

    self.db = Connector(database=database, host=host,
                        user=user, password=password)
    self.create_if_missing = create_if_missing
    self.skip_record_type_check = skip_record_type_check

  ############################
  def _table_name_from_record(self,  record):
    """Infer table name from record."""
    return self.db.table_name_from_record(record)

  ############################
  def _table_exists(self, table_name):
    """Does the specified table exist in the database?"""
    return self.db.table_exists(table_name)
  
  ############################
  def _create_table_from_record(self,  record):
    """Create a new table with one column for each field in the record. Try
    to infer the proper type for each column based on the type of the value
    of the field."""
    self.db.create_table_from_record(record)

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

    # If table doesn't exist, either create or complain, depending on
    # what user specified at initialization.
    table_name = self._table_name_from_record(record)
    if not self._table_exists(table_name):
      if self.create_if_missing:
        self._create_table_from_record(record)
      else:
        logging.error('Table "%s" does not exist, and create_if_missing==False',
                      table_name)
        return

    # Write the record
    self._write_record(record)
