#!/usr/bin/env python3

import json
import logging
import pprint
import sys
import time

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord
from logger.utils import timestamp
from logger.utils.formats import Text
from logger.writers.writer import Writer


INFLUXDB_AUTH_TOKEN = INFLUXDB_ORG = INFLUXDB_URL = None
try:
  from database.settings import INFLUXDB_AUTH_TOKEN, INFLUXDB_ORG, INFLUXDB_URL
  INFLUXDB_SETTINGS_FOUND = True
except (ModuleNotFoundError, ImportError):
  INFLUXDB_SETTINGS_FOUND = False

try:
  from influxdb_client import InfluxDBClient
  from influxdb_client.client.write_api import ASYNCHRONOUS
  INFLUXDB_CLIENT_FOUND = True
except (ModuleNotFoundError, ImportError):
  INFLUXDB_CLIENT_FOUND = False

import time

################################################################################
class InfluxDBWriter(Writer):
  """Write to the specified file. If filename is empty, write to stdout."""
  def __init__(self, bucket_name, measurement_name=None):
    """
    Write data records to the InfluxDB.
    ```
    bucket_name - the name of the bucket in InfluxDB.  If the bucket does
                  not exists then this writer will try to create it.

    measurement_name - optional measurement name to use. If not provided,
                  writer will use the record's data_id
    ```
    """
    super().__init__(input_format=Text)

    if not INFLUXDB_SETTINGS_FOUND:
      raise RuntimeError('File database/settings.py not found. '
                         'InfluxDB functionality is not available. Have '
                         'you copied over database/settings.py.dist '
                         'to database/settings.py and followed the '
                         'configuration instructions in it?')
    if not INFLUXDB_CLIENT_FOUND:
      raise RuntimeError('Python module influxdb_client not found. Please '
                         'install using "pip install influxdb_client" prior '
                         'to using InfluxDBWriter.')

    self.client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_AUTH_TOKEN, org=INFLUXDB_ORG)

    self.bucket_name = bucket_name
    self.measurement_name = measurement_name

    # get the orgID from the name:
    try:
      self.organizations_api = self.client.organizations_api()
      orgs = self.organizations_api.find_organizations()
    except:
      raise RuntimeError('Error connecting to the InfluxDB API. '
                         'Please confirm that InfluxDB is running and '
                         'that the authentication token is correct.')

    our_org = next((org for org in orgs if org.name == INFLUXDB_ORG), None)

    if not our_org:
      raise RuntimeError('Can not find the organization "' + INFLUXDB_ORG + '" in InfluxDB')

    self.org_id = our_org.id

    # get the bucketID from the name:
    self.bucket_api = self.client.buckets_api()
    bucket = self.bucket_api.find_bucket_by_name(bucket_name)

    # if the bucket does not exist then try to create it
    if not bucket:
      try:
        new_bucket = self.bucket_api.create_bucket(bucket_name=bucket_name, org_id=self.org_id)
        logging.info('Creating new bucket for: %s', bucket_name)
        self.bucket_id = new_bucket.id
      except:
        raise RuntimeError('Can not create bucket in InfluxDB for ' + bucket_name)
    else:
      self.bucket_id = bucket.id

    self.write_api = self.client.write_api(write_options=ASYNCHRONOUS)

  ############################
  def write(self, record):
    """Note: Assume record is a dict or DASRecord or list of
    dict/DASRecord. In each record look for 'fields', 'data_id' and
    'timestamp' (UTC epoch seconds). If data_id is missing, use the
    bucket_name we were initialized with.
    """

    def record_to_influx(record):
      """Put a single record into the format that InfluxDB wants."""
      if type(record) is DASRecord:
        data_id = record.data_id
        fields = record.fields
        timestamp = record.timestamp
      else:
        data_id = record.get('data_id', None)
        fields = record.get('fields', {})
        timestamp = record.get('timestamp', None) or time.time()
      influxDB_record = {
        'measurement': self.measurement_name or data_id,
        'tags': {'sensor': data_id or self.measurement_name or self.bucket_name}, 
        'fields': fields,
        'time': int(timestamp*1000000000)
      }
      return influxDB_record

    if not record:
      return

    logging.debug('InfluxDBWriter writing record: %s', record)

    if not type(record) in [dict, list, DASRecord]:
      logging.warning('InfluxDBWriter received record that was not dict, '
                      'list or DASRecord format. Type %s: %s',
                      type(record), str(record))
    try:
      if type(record) in [list, DASRecord]:
        influxDB_record = [record_to_influx(r) for r in record]
      else:
        influxDB_record = record_to_influx(record)
      #logging.info('influxdb\n bucket: %s\nrecord: %s',
      #             self.bucket_name, pprint.pformat(influxDB_record))
      self.write_api.write(self.bucket_id, self.org_id, influxDB_record)

    except Exception as e:
      logging.warning('InfluxDBWriter exception: %s', str(e))
      logging.warning('InfluxDBWriter could not ingest record '
                      'type %s: %s', type(record), str(record))
