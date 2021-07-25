#!/usr/bin/env python3

import os.path
import sys

from datetime import timezone

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.timestamp import time_str, DATE_FORMAT  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402


class FileWriter(Writer):
    """Write to the specified file. If filename is empty, write to stdout."""

    def __init__(self, filename=None, mode='a', delimiter='\n', flush=True,
                 split_by_time=False, time_format='-' + DATE_FORMAT,
                 time_zone=timezone.utc, create_path=True):
        """Write text records to a file. If no filename is specified, write to
        stdout.
        ```
        filename     Name of file to write to. If None, write to stdout

        mode         Mode with which to open file. 'a' by default to append, but
                     can also be 'w' to truncate, 'ab' to append in binary
                     mode, or any other valid Python write file mode.

        delimiter    By default, append a newline after each record
                     written. Set to None to disable appending any record
                     delimiter.

        flush        If True, flush after each write.

        split_by_time Create a separate text file for each (by default)
                     day, appending a -YYYY-MM-DD string to the specified
                     filename. By overridding time_format, other split
                     intervals, such as hourly or monthly, may be imposed.

        time_format  By default ISO 8601-compliant '-%Y-%m-%d'. If,
                     e.g. '-%Y-%m' is used, files will be split by month;
                     if -%y-%m-%d:%H' is specified, splits will be
                     hourly. If '%y+%j' is specified, splits will be
                     daily, but named via Julian date.

        time_zone    Time zone to use for determining splits. By default UTC.

        create_path Create directory path to file if it doesn't exist ```
        ```

        """
        super().__init__()

        self.filename = filename
        self.mode = mode
        self.delimiter = delimiter
        self.flush = flush
        self.split_by_time = split_by_time
        self.time_format = time_format
        self.time_zone = time_zone

        if split_by_time and not filename:
            raise ValueError('FileWriter: filename must be specified if '
                             'split_by_time is True.')

        # If we're splitting by time, keep track of current file suffix so
        # we know when to roll over.
        self.file_suffix = None
        self.file = None

        # A hook to aid in debugging; should be None to use system time.
        self.timestamp = None

        # If directory doesn't exist, try to create it
        if filename and create_path:
            file_dir = os.path.dirname(filename)
            if file_dir:
                os.makedirs(file_dir, exist_ok=True)

    ############################
    def _get_file_suffix(self):
        """Return a string to be used for the file suffix."""

        # Note: the self.timestamp variable exists for debugging, and
        # should be left as None in actual use, which tells the time_str
        # method to use current system time.
        return time_str(timestamp=self.timestamp, time_zone=self.time_zone,
                        time_format=self.time_format)

    ############################
    def _set_file(self, filename):
        """Set the current file to the specified filename."""

        # If they haven't given us a filename, we'll write to stdout
        if self.filename is None:
            self.file = sys.stdout
            return

        # If here, we have a filename. If we already have a file open,
        # close it, then open the new one.
        if self.file:
            self.file.close()

        # Finally, open the specified file with the specified mode
        self.file = open(filename, self.mode)

    ############################
    def write(self, record):
        """ Write out record, appending a newline at end."""
        if record is None:
            return

        # If we've got a list, assume it's a list of records. Recurse,
        # calling write() on each of the list elements in order.
        if isinstance(record, list):
            for single_record in record:
                self.write(single_record)
            return

        # If we're splitting by some time interval, see if it's time to
        # roll over to a new file.
        if self.split_by_time:
            new_file_suffix = self._get_file_suffix()
            if new_file_suffix != self.file_suffix:
                self.file_suffix = new_file_suffix
                self._set_file(self.filename + new_file_suffix)

        # If we're not splitting by intervals, still check that we've got
        # a file open we can write to. If not, open it.
        else:
            if not self.file:
                self._set_file(self.filename)

        if isinstance(record, dict):
            record = str(record)

        # Write the record and flush if requested
        self.file.write(record)
        if self.delimiter is not None:
            self.file.write(self.delimiter)
        if self.flush:
            self.file.flush()
