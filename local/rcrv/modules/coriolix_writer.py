#!/usr/bin/env python3

import logging
import pprint
import sys
import time
from datetime import datetime, timezone

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.formats import Python_Record
from logger.utils.das_record import DASRecord
from logger.writers.writer import Writer

# Don't freak out if we can't find database settings - unless they actually
# try to instantiate a DatabaseWriter.
try:
  from local.rcrv.modules.coriolix_connector import POSTGRES_ENABLED, CORIOLIXConnector as Connector
  from local.rcrv.settings import CORIOLIX_DATABASE, CORIOLIX_DATABASE_HOST
  from local.rcrv.settings import CORIOLIX_DATABASE_USER, CORIOLIX_DATABASE_PASSWORD
  from psycopg2.extensions import AsIs
  CORIOLIX_SETTINGS_FOUND = True
except ModuleNotFoundError:
  CORIOLIX_SETTINGS_FOUND = False
  CORIOLIX_DATABASE = CORIOLIX_DATABASE_HOST = None
  CORIOLIX_DATABASE_USER = CORIOLIX_DATABASE_PASSWORD = None

################################################################################
class CORIOLIXWriter(Writer):
  def __init__(self,
               data_table,
               data_model=None,
               data_fieldnames=None,
               host=CORIOLIX_DATABASE_HOST,
               database=CORIOLIX_DATABASE, 
               user=CORIOLIX_DATABASE_USER,
               password=CORIOLIX_DATABASE_PASSWORD):
    """Write the passed record to specified table in the CORIOLIX database.

    ```
    data_table - To which table the received records should be written.

    data_model - What data model to use for the records.

    data_fieldnames - Which fields should be written to the table.

    host - hostname:port at which to connect.

    database - Database on host to which records should be written.

    user - User to use when connecting to the database.

    password - Password for the specified database user.

    ```

    Alternatively, it can accept and process a list of either of the
    above, which it will write sequentially.
    """
    super().__init__(input_format=Python_Record)

    if not CORIOLIX_SETTINGS_FOUND:
     raise RuntimeError('File local/rcrv/settings.py not found. CORIOLIX '
                        'functionality is not available. Have you copied '
                        'over local/rcrv/settings.py.dist to local/rcrv/settings.py?')
    if not POSTGRES_ENABLED:
     raise RuntimeError('Postgres Database not configured in local.rcrv.modules.coriolix_connector.py; '
                        'CORIOLIXWriter unavailable.')
    
    self.db = Connector(database=database, host=host,
                       user=user, password=password)

    # logging.warning(self.db.table_exists(data_table))
    if not self.db.table_exists(data_table):
      raise RuntimeError("The sensor data table {} does not exists.".format(data_table))

    self.data_table = data_table
    self.data_fieldnames = data_fieldnames.split(',')

    # logging.info('Data table: %s', data_table)

    self.data_table = data_table
    logging.info('Data table: %s', data_table)

  ############################
  def _write_record(self, record):
    """Write DASrecord to table.
    """
    # logging.warning('CORIOLIXWriter writing record to table: %s\n%s', self.data_table, record)

    record.fields['datetime'] = datetime.fromtimestamp(record.timestamp, timezone.utc)
    record.fields['sensor_id'] = record.data_id

    fields = ['datetime', 'sensor_id'] + self.data_fieldnames

    values = None
    try:
      values = [record.fields[field] for field in fields]
    except Exception as e:
      logging.error("Data record does not contain data values for all specified data fields\nExpected: %s, Missing: %s", ','.join(self.data_fieldnames), ','.join((list(set(self.data_fieldnames) - set(list(record.fields.keys()))))))
      del record.fields['datetime']
      return

    insert_statement = 'insert into {} (%s) values %s'.format(self.data_table)

    cursor = self.db.connection.cursor()
    # logging.warning(cursor.mogrify(insert_statement, (AsIs(','.join(fields)), tuple(values))))
    try:
        cursor.execute(insert_statement, (AsIs(','.join(fields)), tuple(values)))
    except Exception as e:
        logging.error("Unable to insert data: %sSQL insert statement: %s", e, cursor.mogrify(insert_statement, (AsIs(','.join(fields)), tuple(values))))
        
    del record.fields['datetime']

  ############################
  def write(self, record):
    """Write out record. Accept a DASRecord or a dict, or a list of either
    of those.
    """
    if not record:
      return

    # If we've got a list, hope it's a list of records. Recurse,
    # calling write() on each of the list elements in order.
    if type(record) is list:
      for single_record in record:
        self.write(single_record)
      return

    # If we've been passed a DASRecord, things are easy: write it and return.
    if type(record) is DASRecord:
      self._write_record(record)
      return
    
    if not type(record) is dict:
      logging.error('Record passed to CORIOLIXWriter is not of type '
                    '"DASRecord" or dict; is type "%s"', type(record))
      return

    # If here, our record is a dict, figure out whether it is a top-level
    # field dict or not.
    data_id = record.get('data_id', None)
    timestamp = record.get('timestamp', time.time())
    fields = record.get('fields', None)
    if fields is None:
      logging.info('Dict record passed to CORIOLIXWriter has no "fields" '
                    'key, which either means it\'s not a dict you should be '
                    'passing, or it is in the old "field_dict" format that '
                    'assumes key:value pairs are at the top level.')
      logging.info('The record in question: %s', str(record))
      return

    das_record = DASRecord(data_id=data_id, timestamp=timestamp, fields=fields)
    self._write_record(das_record)
    return
