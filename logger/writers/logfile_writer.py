#!/usr/bin/env python3

import json
import logging
import re
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.utils import timestamp  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402
from logger.writers.file_writer import FileWriter  # noqa: E402


class LogfileWriter(Writer):
    """Write to the specified filebase, with datestamp appended. If filebase
    is a <regex>:<filebase> dict, write records to every filebase whose
    regex appears in the record.
    """
    def __init__(self, filebase=None, flush=True,
                 time_format=timestamp.TIME_FORMAT,
                 date_format=timestamp.DATE_FORMAT,
                 split_char=' ', suffix='', header=None,
                 header_file=None, rollover_hourly=False,
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

        flush           If True (default), flush after every write() call

        date_fomat      A strftime-compatible string, such as '%Y-%m-%d';
                        defaults to whatever's defined in
                        utils.timestamps.DATE_FORMAT.

        split_char      Delimiter between timestamp and rest of message

        suffix          string to apply to the end of the log filename

        header          Add the specified header string to each file.

        header_file     Add the content of the specified file to each file.

        rollover_hourly Set files to truncate by hour.  By default files will
                        truncate by day

        quiet           If True, don't complain if a record doesn't match
                        any mapped prefix
        ```
        """
        self.filebase = filebase
        self.flush = flush
        self.time_format = time_format
        self.date_format = date_format
        self.split_char = split_char
        self.suffix = suffix
        self.header = header
        self.header_file = header_file
        self.rollover_hourly = rollover_hourly
        self.quiet = quiet

        # If our filebase is a dict, we're going to be doing our
        # fancy pattern->filebase mapping.
        self.do_filebase_mapping = type(self.filebase) == dict

        if self.do_filebase_mapping:
            # Do our matches faster by precompiling
            self.compiled_filebase_map = {
                pattern: re.compile(pattern) for pattern in self.filebase
            }
        self.current_filename = {}
        self.writer = {}

    ############################
    def write(self, record):
        if record is None:
            return
        if record == '':
            return

        # If we've got a list, hope it's a list of records. Recurse,
        # calling write() on each of the list elements in order.
        if isinstance(record, list):
            for single_record in record:
                self.write(single_record)
            return

        # Look for the timestamp
        if isinstance(record, DASRecord):  # If DASRecord or structured dict,
            ts = record.timestamp          # convert to JSON before writing
            record = record.as_json()

        elif isinstance(record, dict):
            ts = record.get('timestamp', None)
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
        hr_str = self.rollover_hourly and \
            timestamp.date_str(ts, date_format='_%H00') or ""
        date_str = timestamp.date_str(ts, date_format=self.date_format)
        time_str = date_str + hr_str + self.suffix
        logging.debug('LogfileWriter time_str: %s', time_str)

        # Figure out where we're going to write
        if self.do_filebase_mapping:
            matched_patterns = [self.write_if_match(record, pattern, time_str)
                                for pattern in self.filebase]
            if True not in matched_patterns:
                if not self.quiet:
                    logging.warning(f'No patterns matched in LogfileWriter '
                                    f'options for record "{record}"')
        else:
            pattern = 'fixed'  # just an arbitrary fixed pattern
            filename = self.filebase + '-' + time_str
            self.write_filename(record, pattern, filename)

    ############################
    def write_if_match(self, record, pattern, time_str):
        """If the record matches the pattern, write to the matching filebase."""
        # Find the compiled regex matching the pattern
        regex = self.compiled_filebase_map.get(pattern, None)
        if not regex:
            logging.error(f'System error: found no regex pattern matching "{pattern}"!')
            return None

        # If the pattern isn't in this record, go home quietly
        if regex.search(record) is None:
            return None

        # Otherwise, we write.
        filebase = self.filebase.get(pattern, None)
        if filebase is None:
            logging.error(f'System error: found no filebase matching pattern "{pattern}"!')
            return None

        filename = filebase + '-' + time_str
        self.write_filename(record, pattern, filename)
        return True

    ############################
    def write_filename(self, record, pattern, filename):
        """Write record to filename. If it's the first time we're writing to
        this filename, create the appropriate FileWriter and insert it into
        the map for the relevant pattern."""

        # Are we currently writing to this file? If not, open/create it.
        if not filename == self.current_filename.get(pattern, None):
            logging.info('LogfileWriter opening new file: %s', filename)
            self.current_filename[pattern] = filename
            self.writer[pattern] = FileWriter(filename=filename,
                                              header=self.header,
                                              header_file=self.header_file,
                                              flush=self.flush)
        # Now, if our logic is correct, should *always* have a matching_writer
        matching_writer = self.writer.get(pattern)
        matching_writer.write(record)
