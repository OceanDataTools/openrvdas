#!/usr/bin/env python3

import time
import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord  # noqa: E402
from logger.utils.formats import Text  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402

INFLUXDB_AUTH_TOKEN = INFLUXDB_ORG = INFLUXDB_URL = None
try:
    from database.influxdb.settings import INFLUXDB_AUTH_TOKEN, INFLUXDB_ORG  # noqa: E402
    from database.influxdb.settings import INFLUXDB_URL  # noqa: E402
    INFLUXDB_SETTINGS_FOUND = True
except (ModuleNotFoundError, ImportError):
    INFLUXDB_SETTINGS_FOUND = False

try:
    from influxdb_client import InfluxDBClient  # noqa: E402
    from influxdb_client.client.write_api import ASYNCHRONOUS  # noqa: E402
    INFLUXDB_CLIENT_FOUND = True
except (ModuleNotFoundError, ImportError):
    INFLUXDB_CLIENT_FOUND = False


class InfluxDBWriter(Writer):
    """Write to the specified file. If filename is empty, write to stdout."""

    def __init__(self, bucket_name, measurement_name=None,
                 auth_token=INFLUXDB_AUTH_TOKEN,
                 org=INFLUXDB_ORG, url=INFLUXDB_URL):
        """Write data records to the InfluxDB.
        ```
        bucket_name - the name of the bucket in InfluxDB.  If the bucket does
                  not exists then this writer will try to create it.

        measurement_name - optional measurement name to use. If not provided,
                  writer will use the record's data_id.

        auth_token - The auth token required by the InfluxDB instance. If omitted,
                  will look for value in imported INFLUXDB_AUTH_TOKEN and throw
                  an exception if it is not found.

        org - The organization to associate with in the InfluxDB
                  instance. If omitted, will look for value in imported
                  INFLUXDB_ORG and throw an exception if it is not found.

        url - The URL at which to connect with the InfluxDB instance. If
                  omitted, will look for value in imported INFLUXDB_ORG
                  and throw an exception if it is not found.
        ```
        """
        super().__init__(input_format=Text)
        if not auth_token:
            raise RuntimeError('No auth token specified in InfluxDBWriter and '
                               'none found in database/influxdb/settings.py. Have '
                               'you copied over database/influxdb/settings.py.dist '
                               'to database/influxdb/settings.py and followed the '
                               'configuration instructions in it?')
        if not org:
            raise RuntimeError('No organization specified in InfluxDBWriter and '
                               'none found in database/influxdb/settings.py. Have '
                               'you copied over database/influxdb/settings.py.dist '
                               'to database/influxdb/settings.py and followed the '
                               'configuration instructions in it?')
        if not url:
            raise RuntimeError('No URL specified in InfluxDBWriter and '
                               'none found in database/influxdb/settings.py. Have '
                               'you copied over database/influxdb/settings.py.dist '
                               'to database/influxdb/settings.py and followed the '
                               'configuration instructions in it?')

        if not INFLUXDB_SETTINGS_FOUND:
            raise RuntimeError('File database/influxdb/settings.py not found. '
                               'InfluxDB functionality is not available. Have '
                               'you copied over database/influxdb/settings.py.dist '
                               'to database/influxdb/settings.py and followed the '
                               'configuration instructions in it?')
        if not INFLUXDB_CLIENT_FOUND:
            raise RuntimeError('Python module influxdb_client not found. Please '
                               'install using "pip install influxdb_client" prior '
                               'to using InfluxDBWriter.')

        self.auth_token = auth_token
        self.org = org
        self.url = url
        self.bucket_name = bucket_name
        self.measurement_name = measurement_name
        self.write_api = None

        # TODO: retry connecting if connection dies while writing.
        self._connect()

    ############################
    def _connect(self):

        while not self.write_api:
            client = InfluxDBClient(url=self.url, token=self.auth_token, org=self.org)

            # get the orgID from the name:
            try:
                organizations_api = client.organizations_api()
                orgs = organizations_api.find_organizations()
            except BaseException:
                self.client = None
                logging.warning('Error connecting to the InfluxDB API. '
                                'Please confirm that InfluxDB is running and '
                                'that the authentication token is correct.'
                                'Sleeping before trying again.')
                time.sleep(5)
                continue

            # Look up the organization id for our org
            our_org = next((org for org in orgs if org.name == self.org), None)
            if not our_org:
                logging.fatal('Can not find org "%s" in InfluxDB', self.org)
                raise RuntimeError('Can not find org "%s" in InfluxDB' % self.org)
            self.org_id = our_org.id

            # get the bucketID from the name:
            bucket_api = client.buckets_api()
            bucket = bucket_api.find_bucket_by_name(self.bucket_name)

            # if the bucket does not exist then try to create it
            if bucket:
                self.bucket_id = bucket.id
            else:
                try:
                    logging.info('Creating new bucket for: %s', self.bucket_name)
                    new_bucket = bucket_api.create_bucket(bucket_name=self.bucket_name,
                                                          org_id=self.org_id)
                    self.bucket_id = new_bucket.id
                except BaseException:
                    logging.fatal('Can not create InfluxDB bucket "%s"', self.bucket_name)
                    raise RuntimeError('Can not create InfluxDB bucket "%s"'
                                       % self.bucket_name)

            self.write_api = client.write_api(write_options=ASYNCHRONOUS)

    ############################
    def write(self, record):
        """Note: Assume record is a dict or DASRecord or list of
        dict/DASRecord. In each record look for 'fields', 'data_id' and
        'timestamp' (UTC epoch seconds). If data_id is missing, use the
        bucket_name we were initialized with.
        """

        def record_to_influx(record):
            """Put a single record into the format that InfluxDB wants."""
            if isinstance(record, DASRecord):
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
                'time': int(timestamp * 1000000000)
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
            if isinstance(record, list):
                influxDB_record = [record_to_influx(r) for r in record]
            else:
                influxDB_record = record_to_influx(record)
            # logging.info('influxdb\n bucket: %s\nrecord: %s',
            #             self.bucket_name, pprint.pformat(influxDB_record))
            self.write_api.write(self.bucket_id, self.org_id, influxDB_record)

        except Exception as e:
            logging.warning('InfluxDBWriter exception: %s', str(e))
            logging.warning('InfluxDBWriter could not ingest record '
                            'type %s: %s', type(record), str(record))
