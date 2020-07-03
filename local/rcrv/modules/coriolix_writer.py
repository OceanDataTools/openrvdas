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
  from local.rcrv.modules.coriolix_connector import POSTGRES_ENABLED, CORIOLIXConnector as Connector
  from local.rcrv.settings import CORIOLIX_DATABASE, CORIOLIX_DATABASE_HOST
  from local.rcrv.settings import CORIOLIX_DATABASE_USER, CORIOLIX_DATABASE_PASSWORD
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
               password=CORIOLIX_DATABASE_PASSWORD,
               save_source=True):
    """Write to the passed record to a Postgres database table.

    ```
    data_table - To which table the received records should be written

    data_model - If specified, what data model to use for the records. If
        not specified, writer will try to figure it out on its own.

    data_fieldnames - Which fields should be written to the table. If not
        specified, try to write all fields that match fields in the model.

    host - hostname:port at which to connect

    database - Database on host to which records should be written
    ```

    Expects passed source records to be in one of two formats:

    1) DASRecord

    2) A dict encoding optionally a source data_id and timestamp and a
       mandatory 'fields' key of field_name: value pairs. This is the format
       emitted by default by ParseTransform:
    ```
       {
         'data_id': ...,
         'timestamp': ...,
         'fields': {
           field_name: value,    # use default timestamp of 'now'
           field_name: value,
           ...
         }
       }
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
                       user=user, password=password,
                       save_source=save_source)

  ############################
  def _write_record(self, record):
    """Write record to table. Connectors assume we've got a DASRecord, but
    check; if we don't see if it's a suitably-formatted dict that we can
    convert into a DASRecord.
    """
    logging.info('CORIOLIXWriter pretending to write:\n%s', record)

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
      logging.error('Dict record passed to DatabaseWriter has no "fields" '
                    'key, which either means it\'s not a dict you should be '
                    'passing, or it is in the old "field_dict" format that '
                    'assumes key:value pairs are at the top level.')
      logging.error('The record in question: %s', str(record))
      return

    das_record = DASRecord(data_id=data_id, timestamp=timestamp, fields=fields)
    self._write_record(das_record)
    return
