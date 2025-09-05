#!/usr/bin/env python3

import logging
import os.path
import sys
import re
import math
import warnings

from datetime import datetime, timedelta, timezone
from typing import Union

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.timestamp import time_str, DATE_FORMAT  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402

DEFAULT_DATETIME_STR = '-' + DATE_FORMAT


class FileWriter(Writer):
    """Write to the specified file. If filename is empty, write to stdout."""

    def __init__(self,
                 filebase=None,
                 filename=None,          # deprecated
                 mode='a',
                 delimiter='\n',
                 flush=True,
                 split_by_time=False,    # deprecated
                 split_interval=None,
                 header=None,
                 header_file=None,
                 time_format=None,       # deprecated
                 date_format=None,
                 suffix=None,
                 time_zone=timezone.utc,
                 create_path=True,
                 quiet=False,
                 encoding='utf-8',
                 encoding_errors='ignore'):
        """Write text records to a file. If no filename is specified, write to
        stdout.
        ```

        filebase    A filebase string that will be used as for the output
                    filename.

        filename    DEPRECATED Name of file to write to. If None, write to stdout

        mode        Mode with which to open file. 'a' by default to append, but
                    can also be 'w' to truncate, 'ab' to append in binary mode,
                    or any other valid Python write file mode.

        delimiter   By default, append a newline after each record written. Set
                    to None to disable appending any record delimiter.

        flush       If True (default), flush after every write() call

        split_by_time   DEPRECATED Create a separate text file for each (by
                        default) day, appending a -YYYY-MM-DD string to the
                        specified filename. By overridding time_format, other
                        split intervals, such as hourly or monthly, may be
                        imposed.

        split_interval  If set the file will trucate at the specified interval.
                        The value must be a string containing an integer
                        followed by a 'H' (hours) or 'M' (minutes). Default
                        is to not split.

        header          A string to add to the beginning of a new file.

        header_file     A string containing the path to file containing a
                        header string to add to the beginning of a new file.

        time_format     DEPRECATED By default ISO 8601-compliant '-%Y-%m-%d'.
                        If, e.g. '-%Y-%m' is used, files will be split by
                        month; if -%y-%m-%d:%H' is specified, splits will be
                        hourly. If '%y+%j' is specified, splits will be daily,
                        but named via Julian date.  Putting '-' or '.' on the
                        left indicates timestamp suffix, putting it on the
                        right indicates timestamp prefix.  If you put '-' or
                        '.' on both sides, it's handled as a suffix.

        date_fomat      A strftime-compatible string, such as '%Y-%m-%d';
                        defaults to '-' plus whatever's defined in
                        utils.timestamps.DATE_FORMAT.  If the value starts with
                        a '^' character, the string will prepend the file
                        name portion of the filebase

        suffix          A suffix string to add to the log filename.

        time_zone       Timezone to use when constructing the date_format
                        portion of the filenames.

        create_path     Create directory path to file if it doesn't exist.

        quiet           If True, don't complain if a record doesn't match
                        any mapped prefix.

        encoding        'utf-8' by default. If empty or None, do not attempt
                        any decoding and return raw bytes. Other possible
                        encodings are listed in online documentation here:
                        https://docs.python.org/3/library/codecs.html#standard-encodings

        encoding_errors 'ignore' by default. Other error strategies are
                        'strict', 'replace', and 'backslashreplace', described
                        here: https://docs.python.org/3/howto/unicode.html#encodings
        ```
        """

        # --- Deprecated args ---
        if filename is not None:
            filebase = filename
            # warnings.warn(
            #     "`filename` is deprecated, use `filebase` instead",
            #     DeprecationWarning,
            #     stacklevel=2,
            # )
        if split_by_time:
            split_interval = '24H'
            # warnings.warn(
            #     "`split_by_time` is deprecated, use `split_interval` instead",
            #     DeprecationWarning,
            #     stacklevel=2,
            # )
        if time_format is not None:
            # warnings.warn(
            #     "`time_format` is deprecated, use `date_format` instead",
            #     DeprecationWarning,
            #     stacklevel=2,
            # )
            date_format = '^' + time_format[:-1] if time_format.endswith('-') else time_format

        # Can't use split_interval or split_by_time if filebase and filename are None
        if split_interval and filebase is None:
            raise ValueError("filebase must be specified")

        # --- Base file name ---
        self.filebase = filebase

        encoding, encoding_errors = self._resolve_encoding(encoding, encoding_errors, mode)

        super().__init__(quiet=quiet, encoding=encoding,
                         encoding_errors=encoding_errors)

        # --- File settings ---
        self.mode = mode
        self.flush = flush
        self.suffix = suffix or ''
        self.time_zone = time_zone
        self.next_file_split = datetime.now(self.time_zone)

        # --- Delimiter ---
        self.delimiter = self._resolve_delimiter(delimiter)

        # --- Header handling ---
        self.header = self._load_header(header, header_file)

        # --- Split interval ---
        self.split_interval = self._validate_split_interval(split_interval)
        self.split_interval_in_seconds = self._get_split_interval_in_seconds()

        # --- Date/time format ---
        self.date_format = self._validate_date_format(date_format)

        # --- Ensure path exists ---
        if self.filebase and create_path:
            os.makedirs(os.path.dirname(self.filebase), exist_ok=True)

        # --- File state ---
        self.file = None
        self.file_date_format = None

        # A hook to aid in debugging; should be None to use system time.
        self.timestamp = None

    # -----------------------
    # Validation helpers
    # -----------------------
    def _load_header(self, header, header_file):
        if header and header_file:
            raise ValueError("Cannot specify both `header` and `header_file`")

        if 'b' in self.mode and header is not None:
            logging.warning("Ignoring header because file mode is binary")
            return None

        if 'b' in self.mode and header is not None:
            logging.warning("Ignoring header because file mode is binary")
            return None
        # Case 1: simple string header
        if header:
            return header.rstrip(self.delimiter) + self.delimiter if self.delimiter else header

        # Case 2: header_file is a single path
        if header_file:
            try:
                with open(header_file, "r", encoding="utf-8") as hf:
                    return (
                        hf.read().strip().rstrip(self.delimiter) + self.delimiter
                        if self.delimiter
                        else hf.read().strip()
                    )
            except OSError as e:
                raise ValueError(f"Error reading header_file {header_file}: {e}")

        return None

    def _validate_split_interval(self, split_interval):
        if split_interval is None:
            return None
        if not isinstance(split_interval, str):
            raise ValueError("split_interval must be a string like '1H' or '30M'")
        if not split_interval.endswith(("H", "M")):
            raise ValueError("must be an integer followed by 'H' or 'M'")
        try:
            return (int(split_interval[:-1]), split_interval[-1])
        except ValueError:
            raise ValueError("must be an integer followed by 'H' or 'M'")
        return None

    def _resolve_encoding(self, encoding, encoding_errors, mode):
        if 'b' in mode and (encoding or encoding_errors) is not None:
            logging.warning("Ignoring encoding and encoding_errors because"
                            " file mode is binary")
            return None, None
        return encoding, encoding_errors

    def _resolve_delimiter(self, delimiter):
        if 'b' in self.mode and delimiter is not None:
            logging.warning("Ignoring delimiter because file mode is binary")
            return None

        if delimiter:
            delimiter = delimiter.encode("utf-8").decode("unicode_escape")

        return delimiter

    def _validate_date_format(self, date_format):

        if not self.split_interval:
            return date_format or ""

        if self.split_interval[1] == "H":
            hours = self.split_interval[0]    # strip trailing H
            even_days = hours % 24 == 0  # check multiple of 24

            if not date_format:
                return DEFAULT_DATETIME_STR if even_days else DEFAULT_DATETIME_STR + "T%H00"

            required = {"%Y", "%m", "%d"} if even_days else {"%Y", "%m", "%d", "%H"}
            found = set(re.findall(r"%[a-zA-Z]", date_format))
            if not required.issubset(found):
                reason = 'years, months and days' if even_days else 'years, months, days and hours'
                raise ValueError(f"date_format must include provisions for {reason}")
            return date_format

        if self.split_interval[1] == "M":
            minutes = self.split_interval[0]     # strip trailing M
            even_hours = minutes % 60 == 0  # check multiple of 60
            return DEFAULT_DATETIME_STR + "T%H00" if even_hours else DEFAULT_DATETIME_STR + "T%H%M"

            required = {"%Y", "%m", "%d", "%H"} if even_hours else {"%Y", "%m", "%d", "%H", "%M"}
            found = set(re.findall(r"%[a-zA-Z]", date_format))
            if not required.issubset(found):
                reason = (
                    'years, months, days and hours'
                    if even_days
                    else 'years, months, days, hours and minutes'
                )
                raise ValueError(f"date_format must include provisions for {reason}")
            return date_format

        return DEFAULT_DATETIME_STR  # fallback

    ############################
    def __del__(self):
        if hasattr(self, 'file') and self.file:
            self.file.close()

    ############################
    def _get_split_interval_in_seconds(self):

        if not self.split_interval:
            return 0

        if self.split_interval[1] == 'H':
            return self.split_interval[0] * 3600

        if self.split_interval[1] == 'M':
            return self.split_interval[0] * 60

        return 0

    ############################
    def _get_file_date_format(self):
        """Return a string to be used for the file suffix."""

        # Note: the self.timestamp variable exists for debugging, and
        # should be left as None in actual use, which tells the time_str
        # method to use current system time.

        # if no date_format requested
        # if not self.date_format:
        #     return ""

        # if there is no split interval
        if self.timestamp:
            return time_str(timestamp=self.timestamp,
                            time_zone=self.time_zone,
                            time_format=self.date_format)

        # if the data is being split by N hours
        elif self.split_interval[1] == 'H':  # hour
            timestamp_raw = datetime.now(self.time_zone)
            timestamp_hour = (self.split_interval[0] *
                              math.floor(timestamp_raw.hour/self.split_interval[0]))
            timestamp_proc = timestamp_raw.replace(hour=timestamp_hour, minute=0, second=0)
            self.next_file_split = (timestamp_proc +
                                    timedelta(seconds=self.split_interval_in_seconds))

            return time_str(timestamp=timestamp_proc.timestamp(), time_zone=self.time_zone,
                            time_format=self.date_format)

        # if the data is being split by N minutes
        elif self.split_interval[1] == 'M':  # minute
            timestamp_raw = datetime.now(self.time_zone)
            timestamp_minute = (self.split_interval[0] *
                                math.floor(timestamp_raw.minute/self.split_interval[0]))
            timestamp_proc = timestamp_raw.replace(minute=timestamp_minute, second=0)
            self.next_file_split = (timestamp_proc +
                                    timedelta(seconds=self.split_interval_in_seconds))

            return time_str(timestamp=timestamp_proc.timestamp(), time_zone=self.time_zone,
                            time_format=self.date_format)

        return ""

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
        if file_is_new and self.header:
            self.file.write(self.header)

    ############################
    def write(self, record: Union[str, bytes]):
        """ Write out record, appending a newline at end."""

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            self.digest_record(record)  # inherited from BaseModule()
            return

        if not self.filebase:
            self._set_file(None)

        # If we're splitting by some time interval, see if it's time to
        # roll over to a new file.
        # if self.split_by_time or self.split_interval is not None:
        elif self.split_interval and datetime.now(self.time_zone) > self.next_file_split:
            new_file_date_format = self._get_file_date_format()
            if new_file_date_format != self.file_date_format:
                self.file_date_format = new_file_date_format
                if new_file_date_format.startswith('^'):
                    self._set_file(
                        os.path.dirname(self.filebase)
                        + new_file_date_format[1:]
                        + os.path.basename(self.filebase)
                        + self.suffix
                    )
                else:
                    self._set_file(self.filebase + new_file_date_format + self.suffix)

        # If we're not splitting by intervals, still check that we've got
        # a file open we can write to. If not, open it.
        else:
            if not self.file:
                self._set_file(self.filebase + self.suffix)

        # Write the record and flush if requested
        self.file.write(record)
        if self.delimiter is not None:
            self.file.write(self.delimiter)
        if self.flush:
            self.file.flush()
