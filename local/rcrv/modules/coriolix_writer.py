#!/usr/bin/env python3

import logging
import sys
import time
from datetime import datetime, timezone

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402

try:
    import psycopg2
    from psycopg2.extensions import AsIs  # noqa: E402
    POSTGRES_ENABLED = True
except ModuleNotFoundError:
    POSTGRES_ENABLED = False

try:
    from local.rcrv.settings import CORIOLIX_DATABASE, CORIOLIX_DATABASE_HOST  # noqa: E402
    from local.rcrv.settings import CORIOLIX_DATABASE_USER, CORIOLIX_DATABASE_PASSWORD  # noqa: E402
    CORIOLIX_SETTINGS_FOUND = True
except ModuleNotFoundError:
    CORIOLIX_SETTINGS_FOUND = False
    CORIOLIX_DATABASE = CORIOLIX_DATABASE_HOST = None
    CORIOLIX_DATABASE_USER = CORIOLIX_DATABASE_PASSWORD = None


################################################################################
class CORIOLIXWriter(Writer):
    def __init__(self,
                 data_table,
                 host=CORIOLIX_DATABASE_HOST,
                 database=CORIOLIX_DATABASE,
                 user=CORIOLIX_DATABASE_USER,
                 password=CORIOLIX_DATABASE_PASSWORD):
        """Write the passed record or list of records to specified table(s) in
        the CORIOLIX database.

        ```
        data_table - a dict where the keys are tables to be written, and values
                 are lists of field names to be written to those tables.

        host - hostname:port at which to connect.

        database - Database on host to which records should be written.

        user - User to use when connecting to the database.

        password - Password for the specified database user.

        ```
        """
        super().__init__()

        if not POSTGRES_ENABLED:
            raise RuntimeError('Python PostgreSQL library \'psycopg2\'not installed '
                               'CORIOLIXWriter unavailable.')

        if not CORIOLIX_SETTINGS_FOUND:
            raise RuntimeError('File local/rcrv/settings.py not found. CORIOLIX '
                               'functionality is not available. Have you copied over '
                               'local/rcrv/settings.py.dist to local/rcrv/settings.py?')

        try:
            self.connection = psycopg2.connect(
                database=database, host=host, user=user, password=password)
            self.connection.set_session(autocommit=True)
        except BaseException:
            raise RuntimeError('Unable to connect to CORIOLIX database.')

        if not isinstance(data_table, dict):
            raise RuntimeError('Parameter "table" must be of type dict; '
                               'found: {}'.format(type(data_table)))
        for table in data_table:
            if not self._table_exists(table):
                raise RuntimeError('The sensor data table {} does not exist.'.format(table))

        self.data_table = data_table

    ############################
    def _table_exists(self, table_name):
        """Does the specified table exist in the database?"""

        with self.connection.cursor() as cursor:
            cursor.execute(
                'SELECT EXISTS ( SELECT FROM information_schema.tables WHERE table_schema '
                '= \'public\' AND table_name = \'%s\')' %
                (table_name))
            if cursor.fetchone()[0]:
                exists = True
            else:
                exists = False
            return exists

    ############################
    def _write_record(self, record):
        """Write DASrecord to database.
        """
        record_datetime = datetime.fromtimestamp(record.timestamp, timezone.utc)
        sensor_id = record.data_id

        # Iterate over the tables we're supposed to write to
        for table, field_names in self.data_table.items():
            table_fields = ['datetime', 'sensor_id'] + field_names
            table_values = [record_datetime, sensor_id]
            try:
                table_values += [record.fields[field] for field in field_names]

            # Skip if we don't have the fields needed to write this table
            except KeyError:
                continue

            # Write to the table in question
            insert_statement = 'insert into {} (%s) values %s'.format(table)

            with self.connection.cursor() as cursor:
                try:
                    cursor.execute(insert_statement,
                                   (AsIs(','.join(table_fields)), tuple(table_values)))
                except Exception as e:
                    logging.error('Unable to insert data: %s; SQL insert statement: %s',
                                  e, cursor.mogrify(insert_statement,
                                                    (AsIs(','.join(table_fields)),
                                                     tuple(table_values))))

    ############################
    def write(self, record):
        """Write out record. Accept a DASRecord or a dict, or a list of either
        of those.
        """
        if not record:
            return

        # If we've got a list, hope it's a list of records. Recurse,
        # calling write() on each of the list elements in order.
        if isinstance(record, list):
            for single_record in record:
                self.write(single_record)
            return

        # If we've been passed a DASRecord, things are easy: write it and return.
        if isinstance(record, DASRecord):
            self._write_record(record)
            return

        if not isinstance(record, dict):
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

    ############################
    def close(self):
        """Close connection."""
        self.connection.close()
