#!/usr/bin/env python3

import logging
import sys
import time

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import TimestampedReader  # noqa: E402
from logger.utils.formats import Python_Record  # noqa: E402

# Don't freak out if we can't find database settings - unless they actually
# try to instantiate a DatabaseReader.
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
# Read records from specified table.
class DatabaseReader(TimestampedReader):
    """
    Database records to DASRecords.
    """
    ############################

    def __init__(self, fields=None,
                 database=DEFAULT_DATABASE, host=DEFAULT_DATABASE_HOST,
                 user=DEFAULT_DATABASE_USER, password=DEFAULT_DATABASE_PASSWORD,
                 tail=False, sleep_interval=1.0):
        super().__init__(output_format=Python_Record)

        if not DATABASE_SETTINGS_FOUND:
            raise RuntimeError('File database/settings.py not found. Database '
                               'functionality is not available. Have you copied '
                               'over database/settings.py.dist to settings.py?')
        if not DATABASE_ENABLED:
            raise RuntimeError('Database not configured in database/settings.py; '
                               'DatabaseReader unavailable.')

        self.fields = fields
        self.db = Connector(database=database, host=host, user=user,
                            password=password, tail=tail)
        self.sleep_interval = sleep_interval
        self.next_id = 1

    ############################
    def read(self, no_block=False):
        """Read next record in table. Sleep and retry if there's no new
        record to read, unless no_block is specified, in which case, return
        whatever we found."""
        while True:
            record = self.db.read(self.fields)
            if record or no_block:
                return record
            logging.debug('No new record returned by database read. Sleeping')
            time.sleep(self.sleep_interval)

    ############################
    def read_range(self, start=None, stop=None):
        """Read all records beginning at record number 'stop' and ending
        *before* record number 'stop'. If stop is None, read all available
        following records."""

        if stop is not None:
            num_records = stop - start
        else:
            num_records = None
        return self.db.read(self.fields, start=start, num_records=num_records)

    ############################
    def read_time_range(self, start_time=None, stop_time=None):
        """Read the next records from table based on timestamps. If start_time
        is None, use the timestamp of the last read record. If stop_time is None,
        read all records since then."""
        return self.db.read_time(self.fields, start_time=start_time,
                                 stop_time=stop_time)
