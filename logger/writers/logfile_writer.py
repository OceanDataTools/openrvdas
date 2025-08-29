#!/usr/bin/env python3

import os
import json
import logging
import re
import sys
import math
from datetime import datetime, timedelta, timezone

from typing import Union
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.utils import timestamp  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402
from logger.writers.file_writer import FileWriter  # noqa: E402

DEFAULT_DATETIME_STR = '-' + timestamp.DATE_FORMAT


class LogfileWriter(Writer):
    """Write to the specified filebase, with datestamp appended. If filebase
    is a <regex>:<filebase> dict, write records to every filebase whose
    regex appears in the record.
    """
    def __init__(self,
                 filebase=None,
                 delimiter='\n',
                 flush=True,
                 split_interval='24H',
                 header=None,
                 header_file=None,
                 time_format=timestamp.TIME_FORMAT,
                 date_format=DEFAULT_DATETIME_STR,
                 time_zone=timezone.utc,
                 suffix=None,
                 split_char=' ',
                 quiet=False):
        """Write timestamped records to a filebase. The filebase will
        have the current date appended, in keeping with R2R format
        recommendations (http://www.rvdata.us/operators/directory). When the
        timestamped date on records rolls over to next day, create a new file
        with the new date suffix.

        If filebase is a dict of <string>:<filebase> pairs, The writer will
        attempt to match a <string> in the dict to each record it receives.
        It will write the record to the filebase corresponding to the first
        string it matches (Note that the order of comparison is not
        guaranteed!). If no strings match, the record will be written to the
        standalone filebase provided.

        Four formats of records can be written by a LogfileWriter:
            1. A string prefixed by a timestamp
            2. A DASRecord
            3. A dict that has a 'timestamp' key
            4. A list of any of the above

        ```
        filebase        A filebase string to write to or a dict mapping
                        <string>:<filebase>.

        delimiter       A character to trucate each incoming record.

        flush           If True (default), flush after every write() call

        split_interval  If set the file will trucate at the specified interval.
                        The value must be a string containing an integer
                        followed by a 'H' (hours) or 'M' (minutes). Default
                        value is '24H' (daily).

        header          A string to add to the beginning of a new log file
                        or a dict mapping <string>:<header> to select the
                        header string based on the record contents.

        header_file     A string containing the path to file containing a
                        header string to add to the beginning of a new log
                        file or a dict mapping <string>:<header_file> to select
                        the header filepath based on the record contents.

        time_format     The format of the record's timestamp. Defaults to
                        whatever's defined in utils.timestamp.TIME_FORMAT.

        date_fomat      A strftime-compatible string, such as '%Y-%m-%d';
                        defaults to '-' plus whatever's defined in
                        utils.timestamps.DATE_FORMAT.  If the value starts with
                        a '^' character, the string will prepend the file
                        name portion of the filebase

        time_zone       Timezone to use when constructing the date_format
                        portion of the filenames.

        suffix          A suffix string to add to the log filename or a dict
                        mapping <string>:<suffix> to select the suffix to
                        add to a filename based on the record contents.

        split_char      Delimiter between timestamp and rest of message

        quiet           If True, don't complain if a record doesn't match
                        any mapped prefix
        ```
        """

        super().__init__(quiet=quiet)

        self.filebase = filebase
        self.flush = flush
        self.delimiter = delimiter
        self.split_interval = self._validate_split_interval(split_interval)
        self.split_interval_in_seconds = self._get_split_interval_in_seconds()
        self.time_format = time_format
        self.date_format = self._validate_date_format(date_format)
        self.time_zone = time_zone
        self.split_char = split_char
        self.suffix = suffix or ''

        self.header = self._load_header(header, header_file)

        # If our filebase is a dict, we're going to be doing our
        # fancy pattern->filebase mapping.
        self.do_filebase_mapping = isinstance(self.filebase, dict)

        if self.do_filebase_mapping:
            # Do our matches faster by precompiling
            self.compiled_filebase_map = {
                pattern: re.compile(pattern) for pattern in self.filebase
            }

        # If our suffix is a dict, we're going to be doing our
        # fancy pattern->suffix mapping.
        self.do_suffix_mapping = isinstance(self.suffix, dict)

        if self.do_suffix_mapping:
            # Do our matches faster by precompiling
            self.compiled_suffix_map = {
                pattern: re.compile(pattern) for pattern in self.suffix
            }

        # If our header is a dict, we're going to be doing our
        # fancy pattern->header mapping.
        self.do_header_mapping = isinstance(self.header, dict)

        if self.do_header_mapping:
            # Do our matches faster by precompiling
            self.compiled_header_map = {
                pattern: re.compile(pattern) for pattern in self.header
            }

        self.current_filename = {}
        self.writer = {}

    ############################
    def _validate_split_interval(self, split_interval):
        """
        Helper function to validate split_interval
        """
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

    ############################
    def _validate_date_format(self, date_format):
        """
        Helper function to validate date_format
        """

        if not self.split_interval:
            return date_format or ""

        if self.split_interval[1] == "H":
            hours = self.split_interval[0]  # strip trailing H
            even_days = hours % 24 == 0     # check multiple of 24

            if not date_format:
                return DEFAULT_DATETIME_STR if even_days else DEFAULT_DATETIME_STR + "T%H00"

            required = {"%Y", "%m", "%d"} if even_days else {"%Y", "%m", "%d", "%H"}
            found = set(re.findall(r"%[a-zA-Z]", date_format))
            if not required.issubset(found):
                reason = 'years, months and days' if even_days else 'years, months, days and hours'
                raise ValueError(f"date_format must include provisions for {reason}")
            return date_format

        if self.split_interval[1] == "M":
            minutes = self.split_interval[0]  # strip trailing M
            even_hours = minutes % 60 == 0    # check multiple of 60
            return DEFAULT_DATETIME_STR + "T%H00" if even_hours else DEFAULT_DATETIME_STR + "T%H%M"

            required = {"%Y", "%m", "%d", "%H"} if even_hours else {"%Y", "%m", "%d", "%H", "%M"}
            found = set(re.findall(r"%[a-zA-Z]", date_format))
            if not required.issubset(found):
                reason = (
                    "years, months, days and hours"
                    if even_days
                    else "years, months, days, hours and minutes"
                )
                raise ValueError(f"date_format must include provisions for {reason}")
            return date_format

        return DEFAULT_DATETIME_STR  # fallback

    ############################
    def _load_header(self, header, header_file):
        """
        Helper function to verify the header. If a header_file is specified the
        files are read into a local str or dict depending on the data type of
        the header_file argument
        """

        if header and header_file:
            raise ValueError("Cannot specify both `header` and `header_file`")

        # Case 1: simple string header
        if header:
            return header

        # Case 2: header is a dict {key: filepath}
        if isinstance(header, dict):
            result = {}
            for key, header_str in header.items():
                if not isinstance(header_str, str):
                    raise ValueError(f"Invalid string for header key {key}: {header_str!r}")
                result[key] = header_str

            return result

        # Case 3: header_file is a single path
        if isinstance(header_file, str):
            try:
                with open(header_file, "r", encoding="utf-8") as hf:
                    return hf.read().strip()
            except OSError as e:
                raise ValueError(f"Error reading header_file {header_file}: {e}")

        # Case 4: header_file is a dict {key: filepath}
        if isinstance(header_file, dict):
            result = {}
            for key, path in header_file.items():
                if not isinstance(path, str):
                    raise ValueError(f"Invalid path for header key {key}: {path!r}")
                try:
                    with open(path, "r", encoding="utf-8") as hf:
                        result[key] = hf.read().strip()
                except OSError as e:
                    raise ValueError(f"Error reading header_file {path} for key {key}: {e}")
            return result

        return None

    ############################
    def _get_split_interval_in_seconds(self):
        """
        Helper function to calculate the value of the split_interval in seconds
        """

        if not self.split_interval:
            return 0

        if self.split_interval[1] == 'H':
            return self.split_interval[0] * 3600

        if self.split_interval[1] == 'M':
            return self.split_interval[0] * 60

        return 0

    ############################
    def _get_file_date_format(self, ts):
        """
        Helper function to return build the date_format portion of the
        filename.
        """

        # if the data is being split by N hours
        if self.split_interval[1] == 'H':  # hour
            timestamp_raw = datetime.fromtimestamp(ts, tz=self.time_zone)
            timestamp_hour = (self.split_interval[0] *
                              math.floor(timestamp_raw.hour/self.split_interval[0]))
            timestamp_proc = timestamp_raw.replace(hour=timestamp_hour, minute=0, second=0)
            self.next_file_split = (timestamp_proc +
                                    timedelta(seconds=self.split_interval_in_seconds))

            return timestamp.time_str(timestamp=timestamp_proc.timestamp(),
                                      time_zone=self.time_zone,
                                      time_format=self.date_format)

        # if the data is being split by N minutes
        elif self.split_interval[1] == 'M':  # minute
            timestamp_raw = datetime.fromtimestamp(ts, tz=self.time_zone)
            timestamp_minute = (self.split_interval[0] *
                                math.floor(timestamp_raw.minute/self.split_interval[0]))
            timestamp_proc = timestamp_raw.replace(minute=timestamp_minute, second=0)
            self.next_file_split = (timestamp_proc +
                                    timedelta(seconds=self.split_interval_in_seconds))

            return timestamp.time_str(timestamp=timestamp_proc.timestamp(),
                                      time_zone=self.time_zone,
                                      time_format=self.date_format)

        return ""

    ############################
    def fetch_suffix(self, record: str, filename_pattern: str = 'fixed'):
        """
        Return the suffix for the given record.  If filename_pattern os defined
        (because filebase has already matched to a pattern) then that pattern
        is used over what pattern would normally match.
        """

        if not self.do_suffix_mapping:
            return self.suffix

        if filename_pattern != "fixed":
            return_suffix = self.suffix.get(filename_pattern)

            if return_suffix:
                return return_suffix

            if not self.quiet:
                logging.warning('LogfileWriter.fetch_suffix() - no suffix match: "%s"!', record)
            return

        for pattern, regex in self.compiled_suffix_map.items():
            if regex and regex.search(record):
                return self.suffix.get(pattern)

        logging.warning('LogfileWriter.fetch_suffix() - no suffix match: "%s"!', record)

    ############################
    def fetch_header(self, record: str, filename_pattern: str = 'fixed'):
        """
        Return the header for the given record.  If filename_pattern os defined
        (because filebase has already matched to a pattern) then that pattern
        is used over what pattern would normally match.
        """

        if not self.do_header_mapping:
            return self.header

        if filename_pattern != "fixed":
            return_header = self.header.get(filename_pattern)

            if return_header:
                return return_header

            if not self.quiet:
                logging.warning('LogfileWriter.fetch_header() - no header match: "%s"', record)
            return ''

        for pattern, regex in self.compiled_header_map.items():
            if regex and regex.search(record):
                return self.header.get(pattern, '')

        logging.warning('LogfileWriter.fetch_header() - no header match: "%s"', record)
        return ''

    ############################
    def write(self, record: Union[str, DASRecord, dict]):
        if record == '':
            return

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            self.digest_record(record)  # inherited from BaseModule()
            return

        # Look for the timestamp
        if isinstance(record, DASRecord):  # If DASRecord or structured dict,
            ts = record.timestamp          # convert to JSON before writing
            record = record.as_json()

        elif isinstance(record, dict):
            ts = record.get('timestamp')
            if ts is None:
                if not self.quiet:
                    logging.error('LogfileWriter.write() - bad timestamp: "%s"', record)
                return
            record = json.dumps(record)

        elif isinstance(record, str):  # If str, it better begin with time string
            try:  # Try to extract timestamp from record
                time_str = record.split(self.split_char)[0]
                ts = timestamp.timestamp(time_str, time_format=self.time_format)
            except ValueError:
                if not self.quiet:
                    logging.error('LogfileWriter.write() - bad timestamp: "%s"', record)
                    return
        else:
            if not self.quiet:
                logging.error(f'LogfileWriter received badly formatted record. Must be DASRecord, '
                              f'dict, or timestamp-prefixed string. Received: "{record}"')
            return

        # Now parse ts into hour and date strings
        datetime_str = self._get_file_date_format(ts)

        # Figure out where we're going to write
        if self.do_filebase_mapping:
            matched_patterns = [self.write_if_match(record, pattern, datetime_str)
                                for pattern in self.filebase]
            if True not in matched_patterns:
                if not self.quiet:
                    logging.warning(f'No patterns matched in LogfileWriter '
                                    f'options for record "{record}"')
        else:
            pattern = 'fixed'  # just an arbitrary fixed pattern

            suffix = self.fetch_suffix(record, pattern)
            if suffix is None:
                logging.error(f'System error: found no suffix matching record: "{record}"!')
                return None

            if datetime_str.startswith('^'):
                filename = (
                    os.path.dirname(self.filebase)
                    + datetime_str[1:]
                    + os.path.basename(self.filebase)
                    + suffix
                )
            else:
                filename = self.filebase + datetime_str + suffix

            self.write_filename(record, pattern, filename)

    ############################
    def write_if_match(self, record, pattern, datetime_str):
        """
        If the record matches the pattern, write to the matching filebase.
        """

        # Find the compiled regex matching the pattern
        regex = self.compiled_filebase_map.get(pattern)
        if not regex:
            logging.error(f'System error: found no regex matching pattern: "{pattern}"!')
            return None

        # If the pattern isn't in this record, go home quietly
        if regex.search(record) is None:
            return None

        # Otherwise, we write.
        filebase = self.filebase.get(pattern)
        if filebase is None:
            logging.error(f'System error: found no filebase matching pattern "{pattern}"!')
            return None

        suffix = self.fetch_suffix(record, pattern)
        if suffix is None:
            logging.error(f'System error: found no suffix matching pattern: "{pattern}"!')
            return None

        if datetime_str.startswith('^'):
            filename = (
                os.path.dirname(filebase)
                + datetime_str[1:]
                + os.path.basename(filebase)
                + suffix
            )
        else:
            filename = filebase + datetime_str + suffix

        self.write_filename(record, pattern, filename)
        return True

    ############################
    def write_filename(self, record, pattern, filename):
        """
        Write record to filename. If it's the first time we're writing to
        this filename, create the appropriate FileWriter and insert it into
        the map for the relevant pattern.
        """

        # Are we currently writing to this file? If not, open/create it.
        if not filename == self.current_filename.get(pattern):

            # calculate header/header_file and suffix
            header = self.fetch_header(record, pattern) if self.do_header_mapping else self.header

            self.current_filename[pattern] = filename
            self.writer[pattern] = FileWriter(filename=filename,
                                              delimiter=self.delimiter,
                                              header=header,
                                              flush=self.flush)
        # Now, if our logic is correct, should *always* have a matching_writer
        matching_writer = self.writer.get(pattern)
        matching_writer.write(record)
