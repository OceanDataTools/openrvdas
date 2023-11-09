#!/usr/bin/env python3

import logging
import os.path
import sys
import math

from datetime import datetime, timedelta, timezone

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.timestamp import time_str, DATE_FORMAT  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402


class FileWriter(Writer):
    """Write to the specified file. If filename is empty, write to stdout."""

    def __init__(self, filename=None, mode='a', delimiter='\n', flush=True,
                 split_by_time=False, split_interval=None, header=None,
                 header_file=None, time_format='-' + DATE_FORMAT,
                 time_zone=timezone.utc, create_path=True,
                 encoding='utf-8', encoding_errors='ignore'):
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

        split_interval Splits files based on a defined hour (H) or minute (M)
                     time interval such as every 2 hours (2H) or 15 minutes
                     (15M). Currently H and M are the only options. 

        header       Add the specified header string to each file.

        header_file  Add the content of the specified file to each file.

        time_format  By default ISO 8601-compliant '-%Y-%m-%d'. If,
                     e.g. '-%Y-%m' is used, files will be split by month;
                     if -%y-%m-%d:%H' is specified, splits will be
                     hourly. If '%y+%j' is specified, splits will be
                     daily, but named via Julian date.  Putting '-' or '.' on
                     the left indicates timestamp suffix, putting it on the
                     right indicates timestamp prefix.  If you put '-' or '.'
                     on both sides, it's handled as a suffix.

        time_zone    Time zone to use for determining splits. By default UTC.

        create_path  Create directory path to file if it doesn't exist ```

        encoding - 'utf-8' by default. If empty or None, do not attempt any
                decoding and return raw bytes. Other possible encodings are
                listed in online documentation here:
                https://docs.python.org/3/library/codecs.html#standard-encodings

        encoding_errors - 'ignore' by default. Other error strategies are
                'strict', 'replace', and 'backslashreplace', described here:
                https://docs.python.org/3/howto/unicode.html#encodings
        ```

        """
        super().__init__(encoding=encoding,
                         encoding_errors=encoding_errors)

        self.filename = filename
        self.mode = mode
        self.flush = flush
        self.split_by_time = split_by_time
        self.time_format = time_format
        self.time_zone = time_zone
        self.split_interval = None
        self.split_interval_in_seconds = 0
        self.header = None
        self.next_file_split = datetime.now(self.time_zone)

        # 'delimiter' comes in as a (probably escaped) string. We need to
        # unescape it, which means converting to bytes and back.
        if delimiter:
            if self.encoding:
                # NOTE: Technically, it's safe to call _unescape_str() with no
                #       encoding, it just returns the str/bytes/thing
                #       unmodified.  But why tempt fate, right?
                delimiter = self._unescape_str(delimiter)
            else:
                # if encoding has been set to '' or None, we're dealing with
                # raw/binary output.  encode delimiter so we can append it
                # safely in write()
                delimiter = delimiter.encode()
        self.delimiter = delimiter

        if (split_by_time or split_interval) is not None and not filename:
            raise ValueError('FileWriter: filename must be specified if '
                             'split_by_time is specified or split_interval '
                             'is True.')

        if split_interval is not None:
            # Verify the split_interval argument is valid be confirming
            # the last charater is 'H' or 'M' and the preceding characters
            # parse as an integer

            if split_interval[-1] not in ['H','M']:
                raise ValueError('FileWriter: split_interval must be an integer '
                                 'followed by \'H\' or \'M\'.')
            try:
                self.split_interval = (int(split_interval[:-1]), split_interval[-1])
                self.split_interval_in_seconds = self._get_split_interval_in_seconds(split_interval)
            except ValueError:
                raise ValueError('FileWriter: split_interval must be an integer '
                                 'followed by \'H\' or \'M\'.')

        if header is not None and header_file is not None:
            raise ValueError('FileWriter: cannot specify the header and '
                             'header_file arguments.')

        if header is not None:
            if isinstance(header, str):
                self.header = header + '\n'
            else:
                raise ValueError('FileWriter: Unable to add header to data '
                                 'file. header argument must be a string: %s',
                                 header)

        if header_file is not None:
            try:
                with open(header_file, 'r') as file:
                    self.header = file.read()
            except:
                raise ValueError('FileWriter: Unable to add header to data '
                                 'file. header_file argument must be a valid '
                                 'filepath: %s', header_file)

        if self.header is not None and 'b' in mode:
            raise ValueError('FileWriter: Unable to add header to a binary '
                             'data file')

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
    @staticmethod
    def _get_split_interval_in_seconds(split_interval):
        if split_interval[1] == 'H':

            # automatically update default time_format
            if time_format == '-' + DATE_FORMAT:
                self.time_format = '-' + DATE_FORMAT + 'T%H00'

            # raise error if the custom time_format does not contain
            # an hour designation
            elif "%H" not in self.time_format:
                 raise ValueError('FileWriter: time_format must contain a '
                                  'hour designation (%H).')

            return split_interval[0] * 3600

        if split_interval[1] == 'M':

            # automatically update default time_format
            if time_format == '-' + DATE_FORMAT:
                self.time_format = '-' + DATE_FORMAT + 'T%H%M'

            # raise error if the custom time_format does not contain
            # an hour designation
            elif "%H" not in self.time_format or "%M" not in self.time_format:
                 raise ValueError('FileWriter: time_format must contain a '
                                  'hour designation (%H) and minute '
                                  'designation (%M).')

            return split_interval[0] * 60

        return 0


    ############################
    def _get_file_suffix(self):
        """Return a string to be used for the file suffix."""

        # Note: the self.timestamp variable exists for debugging, and
        # should be left as None in actual use, which tells the time_str
        # method to use current system time.

        # if there is no split interval
        if self.split_interval is None:
            return time_str(timestamp=self.timestamp, time_zone=self.time_zone,
                            time_format=self.time_format)

        # if the data is being split by N hours
        elif self.split_interval[1] == 'H': # hour
            timestamp_raw = datetime.now(self.time_zone)
            timestamp_proc = timestamp_raw.replace(hour=self.split_interval[0] * math.floor(timestamp_raw.hour/self.split_interval[0]), minute=0, second=0)
            self.next_file_split = timestamp_proc + timedelta(seconds=self.split_interval_in_seconds)

            return time_str(timestamp=timestamp_proc.timestamp(), time_zone=self.time_zone,
                            time_format=self.time_format)

        # if the data is being split by N minutes
        elif self.split_interval[1] == 'M': # minute
            timestamp_raw = datetime.now(self.time_zone)
            timestamp_proc = timestamp_raw.replace(minute=self.split_interval[0] * math.floor(timestamp_raw.minute/self.split_interval[0]), second=0)
            self.next_file_split = timestamp_proc + timedelta(seconds=self.split_interval_in_seconds)

            return time_str(timestamp=timestamp_proc.timestamp(), time_zone=self.time_zone,
                            time_format=self.time_format)

    ############################
    def _set_file(self, filename):
        """Set the current file to the specified filename."""

        # If they haven't given us a filename, we'll write to stdout
        if filename is None:
            self.file = sys.stdout

            if self.header is not None:
                self.file.write(self.header)

            return

        # If here, we have a filename. If we already have a file open,
        # close it, then open the new one.
        if self.file:
            self.file.close()

        # Check to see if file already exists
        file_is_new = not os.path.isfile(filename)

        # Finally, open the specified file with the specified mode and encoding
        logging.info("opening %s with mode=%s and encoding=%s", filename, self.mode, self.encoding)
        self.file = open(filename, self.mode, encoding=self.encoding)

        # Add header record to file if a header was specified and the file was
        # just created.
        if file_is_new and self.header is not None:
            self.file.write(self.header)

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
        # if self.split_by_time or self.split_interval is not None:
        if self.split_by_time or (self.split_interval and datetime.now(self.time_zone) > self.next_file_split):
            new_file_suffix = self._get_file_suffix()
            if new_file_suffix != self.file_suffix:
                self.file_suffix = new_file_suffix
                if new_file_suffix.startswith('-') or new_file_suffix.startswith('.'):
                    # it's a suffix
                    self._set_file(self.filename + new_file_suffix)
                elif new_file_suffix.endswith('-') or new_file_suffix.endswith('.'):
                    # make it a prefix even though we've called it a suffix
                    # this whole time.
                    self._set_file(os.path.join(os.path.dirname(self.filename),
                                                new_file_suffix + os.path.basename(self.filename)))
                else:
                    # well, this is probably gonna look ugly w/out a separator
                    # character, but go ahead and treat it as a suffix
                    self._set_file(self.filename + new_file_suffix)

        # If we're not splitting by intervals, still check that we've got
        # a file open we can write to. If not, open it.
        else:
            if not self.file:
                self._set_file(self.filename)

        # Write the record and flush if requested
        self.file.write(record)
        if self.delimiter is not None:
            self.file.write(self.delimiter)
        if self.flush:
            self.file.flush()
