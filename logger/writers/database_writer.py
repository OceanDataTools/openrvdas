#!/usr/bin/env python3

import logging
import pprint
import sys
import time

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.formats import Python_Record  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402

# Don't freak out if we can't find database settings - unless they actually
# try to instantiate a DatabaseWriter.
try:
    from database.settings import DATABASE_ENABLED, Connector  # noqa: E402
    from database.settings import DEFAULT_DATABASE, DEFAULT_DATABASE_HOST  # noqa: E402
    from database.settings import DEFAULT_DATABASE_USER, DEFAULT_DATABASE_PASSWORD  # noqa: E402
    DATABASE_SETTINGS_FOUND = True
except ModuleNotFoundError:
    DATABASE_SETTINGS_FOUND = False
    DEFAULT_DATABASE = DEFAULT_DATABASE_HOST = None
    DEFAULT_DATABASE_USER = DEFAULT_DATABASE_PASSWORD = None


class DatabaseWriter(Writer):
    def __init__(self, database=DEFAULT_DATABASE, host=DEFAULT_DATABASE_HOST,
                 user=DEFAULT_DATABASE_USER, password=DEFAULT_DATABASE_PASSWORD,
                 save_source=True):
        """Write to the passed record to a database table. With connectors
        written so far (MySQL and Mongo), writes values in the records as
        timestamped field-value pairs. If save_source=True, also save the
        source record we are passed.

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
        A twist on format (2) is that the values may either be a singleton
        (int, float, string, etc) or a list. If the value is a singleton,
        it is taken at face value. If it is a list, it is assumed to be a
        list of (value, timestamp) tuples, in which case the top-level
        timestamp, if any, is ignored.
        ```
           {
             'data_id': ...,
             'timestamp': ...,
             'fields': {
                field_name: [(timestamp, value), (timestamp, value),...],
                field_name: [(timestamp, value), (timestamp, value),...],
                ...
             }
           }
        ```
        """
        super().__init__(input_format=Python_Record)

        if not DATABASE_SETTINGS_FOUND:
            raise RuntimeError('File database/settings.py not found. Database '
                               'functionality is not available. Have you copied '
                               'over database/settings.py.dist to settings.py?')
        if not DATABASE_ENABLED:
            raise RuntimeError('Database not configured in database/settings.py; '
                               'DatabaseWriter unavailable.')

        self.db = Connector(database=database, host=host,
                            user=user, password=password,
                            save_source=save_source)

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
        if isinstance(record, dict):
            try:
                data_id = record.get('data_id', 'no_data_id')
                timestamp = record.get('timestamp', None)
                fields = record['fields']
                record = DASRecord(data_id=data_id, timestamp=timestamp, fields=fields)
            except KeyError:
                logging.error('Unable to create DASRecord from dict: %s',
                              pprint.pformat(record))
        self.db.write_record(record)

    ############################
    def _delete_table(self, table_name):
        """Delete a table."""
        self.db.delete_table(table_name)

    ############################
    def write(self, record):
        """Write out record. Connectors assume we've got a DASRecord, so check
        what we've got and convert as necessary.
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
            logging.error('Record passed to DatabaseWriter is not of type '
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

        # Now check whether our 'values' are singletons (in which case
        # we've got a single record) or lists of tuples. Shortcut by
        # checking only the first value in our 'fields' dict.
        try:
            first_key, first_value = next(iter(fields.items()))
        except StopIteration:
            # Empty fields
            logging.debug('Empty "fields" dict in record: %s', str(record))
            return

        # If we've got a singleton, it's a single record. Convert to
        # DASRecord and write it out.
        if not isinstance(first_value, list):
            das_record = DASRecord(data_id=data_id, timestamp=timestamp, fields=fields)
            self._write_record(das_record)
            return

        # If we're here, our values (or at least our first one) are lists
        # of (value, timestamp) pairs. First thing we do is
        # reformat the data into a map of
        #
        #        {timestamp: {field:value, field:value],...}}
        values_by_timestamp = {}
        try:
            for field, ts_value_list in fields.items():
                for (timestamp, value) in ts_value_list:
                    if timestamp not in values_by_timestamp:
                        values_by_timestamp[timestamp] = {}
                    values_by_timestamp[timestamp][field] = value
        except ValueError:
            logging.error('Badly-structured field dictionary: %s: %s',
                          field, pprint.pformat(ts_value_list))

        # Now go through each timestamp, generate a DASRecord from its
        # values, and write them.
        for timestamp in sorted(values_by_timestamp):
            das_record = DASRecord(data_id=data_id, timestamp=timestamp,
                                   fields=values_by_timestamp[timestamp])
            self._write_record(das_record)
