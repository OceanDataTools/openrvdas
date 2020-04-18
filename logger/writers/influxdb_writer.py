#!/usr/bin/env python3

import logging
import sys
import json
from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils import timestamp
from logger.utils.formats import Text
from logger.writers.writer import Writer


INFLUXDB_AUTH_TOKEN = INFLUXDB_ORG = INFLUXDB_URL = None
try:
  from database.settings import INFLUXDB_AUTH_TOKEN, INFLUXDB_ORG, INFLUXDB_URL
  INFLUXDB_SETTINGS_FOUND = True
except ModuleNotFoundError:
  INFLUXDB_SETTINGS_FOUND = False

try:
  from influxdb_client import InfluxDBClient
  from influxdb_client.client.write_api import ASYNCHRONOUS
  INFLUXDB_CLIENT_FOUND = True
except ModuleNotFoundError:
  INFLUXDB_CLIENT_FOUND = False

import time

################################################################################
class InfluxDBWriter(Writer):
  """Write to the specified file. If filename is empty, write to stdout."""
  def __init__(self, bucket_name):
    """
    Write data records to the InfluxDB.
    ```
    bucket_name  the name of the bucket in InfluxDB.  If the bucket does
    not exists then this writer will try to create it.
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
    """
    Note: Assume record is a dict or list of dict. Each dict contains a list
    of "fields" and float "timestamp" (UTC epoch seconds)
    """
    if record is None:
      return

    logging.info('InfluxDBWriter writing record: %s', record)

    if type(record) is not dict and type(record) is not list:
      logging.warning('InfluxDBWriter could not ingest record '
                      'type %s: %s', type(record), str(record))

    try:
      if type(record) is list:
        influxDB_record = map(lambda single_record: {"measurement": single_record['data_id'], "tags": {"sensor": single_record['data_id'] }, "fields": single_record['fields'], "time": int(single_record['timestamp']*1000000000) }, record)
      else:
        influxDB_record = {"measurement": record['data_id'], "tags": {"sensor": record['data_id'] }, "fields": record['fields'], "time": int(record['timestamp']*1000000000) }

      self.write_api.write(self.bucket_id, self.org_id, influxDB_record)
      return

    except:
      logging.warning('InfluxDBWriter could not ingest record '
                      'type %s: %s', type(record), str(record))
