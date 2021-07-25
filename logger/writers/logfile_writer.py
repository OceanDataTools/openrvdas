#!/usr/bin/env python3

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import timestamp  # noqa: E402
from logger.utils.formats import Text  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402
from logger.writers.file_writer import FileWriter  # noqa: E402


class LogfileWriter(Writer):
    """Write to the specified file. If filename is empty, write to stdout."""

    def __init__(self, filebase=None, flush=True,
                 time_format=timestamp.TIME_FORMAT,
                 date_format=timestamp.DATE_FORMAT,
                 split_char=' ', suffix='',
                 rollover_hourly=False):
        """Write timestamped text records to file. Base filename will have
        date appended, in keeping with R2R format recommendations
        (http://www.rvdata.us/operators/directory). When timestamped date on
        records rolls over to next day, create new file with new date suffix.
        ```
        filebase        Base name of file to write to. Will have record date
                        appended, e.g.

        flush           If True (default), flush after every write() call

        date_fomat      A strftime-compatible string, such as '%Y-%m-%d';
                        defaults to whatever's defined in
                        utils.timestamps.DATE_FORMAT.

        split_char      Delimiter between timestamp and rest of message

        suffix          string to apply to the end of the log filename

        rollover_hourly Set files to truncate by hour.  By default files will
                        truncate by day
        ```
        """
        super().__init__(input_format=Text)

        self.filebase = filebase
        self.flush = flush
        self.time_format = time_format
        self.date_format = date_format
        self.split_char = split_char
        self.suffix = suffix
        self.rollover_hourly = rollover_hourly

        self.current_date = None
        self.current_hour = None
        self.current_filename = None
        self.writer = None

    ############################
    def write(self, record):
        """Note: Assume record begins with a timestamp string."""
        if record is None:
            return

        # If we've got a list, hope it's a list of records. Recurse,
        # calling write() on each of the list elements in order.
        if isinstance(record, list):
            for single_record in record:
                self.write(single_record)
            return

        if not isinstance(record, str):
            logging.error('LogfileWriter.write() - record not timestamped: %s ',
                          record)
            return

        # Get the timestamp we'll be using
        try:  # Try to extract timestamp from record
            time_str = record.split(self.split_char)[0]
            ts = timestamp.timestamp(time_str, time_format=self.time_format)
        except ValueError:
            logging.error('LogfileWriter.write() - bad timestamp: %s', record)
            return

        # Now parse ts into hour and date strings
        hr_str = self.rollover_hourly and \
            timestamp.date_str(ts, date_format='_%H00') or ""
        date_str = timestamp.date_str(ts, date_format=self.date_format)
        logging.debug('LogfileWriter date_str: %s', date_str)

        # Is it time to create a new file to write to?
        if not self.writer or date_str != self.current_date or hr_str != self.current_hour:
            self.current_filename = self.filebase + '-' + date_str + hr_str + self.suffix
            self.current_date = date_str
            self.current_hour = self.rollover_hourly and hr_str or ""
            logging.info('LogfileWriter opening new file: %s', self.current_filename)
            self.writer = FileWriter(filename=self.current_filename, flush=self.flush)

        logging.debug('LogfileWriter writing record: %s', record)
        self.writer.write(record)
