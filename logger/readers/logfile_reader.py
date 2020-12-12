#!/usr/bin/env python3

import logging
import parse
import sys
import time

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import timestamp  # noqa: E402
from logger.utils.formats import Text  # noqa: E402
from logger.readers.text_file_reader import TextFileReader  # noqa: E402
from logger.readers.reader import TimestampedReader  # noqa: E402


################################################################################
# Open and read single-line records from one or more text files.
class LogfileReader(TimestampedReader):
    """
    Read lines from one or more text files. Sequentially open all
    files that match the file_spec.
    """
    ############################

    def __init__(self, filebase=None, tail=False, refresh_file_spec=False,
                 retry_interval=0.1, interval=0, use_timestamps=False,
                 record_format=None,
                 time_format=timestamp.TIME_FORMAT,
                 date_format=timestamp.DATE_FORMAT,
                 quiet=False):
        """
        ```
        filebase     Possibly wildcarded string specifying files to be opened.
                     Special case: if file_spec is None, read from stdin.

        tail         If False, return None upon reaching end of last file; if
                     True, block upon reaching EOF of last file and wait for
                     more records.

        refresh_file_spec
                     If True, refresh the search for matching filenames when
                     reaching last EOF to see if any new matching files have
                     appeared in the interim.

        retry_interval
                     If tail and/or refresh_file_spec are True, how long to
                     wait before looking to see if any new records or files
                     have shown up.

        interval
                     How long to sleep between returning records. In general
                     this should be zero except for debugging purposes.

        use_timestamps
                     If True, use the timestamps from the log file to determine
                     at what interval each record should be emitted.

        record_format
                     If specified, a custom record format to use for extracting
                     timestamp and record. The default is '{timestamp:ti} {record}'.

        quiet - if not False, don't complain when unable to parse a record.

        ```
        Note that the order in which files are opened will probably be in
        alphanumeric by filename, but this is not strictly enforced and
        depends on how glob returns them.
        """
        super().__init__(output_format=Text)

        if interval and use_timestamps:
            raise ValueError('Can not specify both "interval" and "use_timestamps"')

        self.filebase = filebase
        self.use_timestamps = use_timestamps
        self.record_format = record_format or '{timestamp:ti} {record}'
        self.compiled_record_format = parse.compile(self.record_format)
        self.date_format = date_format
        self.time_format = time_format
        self.tail = tail
        self.refresh_file_spec = refresh_file_spec
        self.quiet = quiet

        # If use_timestamps, we need to keep track of our last_read to
        # know how long to sleep
        self.last_timestamp = 0
        self.last_read = 0

        self._first_msec_timestamp = None
        self.prev_record = None

        # If they give us a filebase, add wildcard to match its suffixes;
        # otherwise, we'll pass on the empty string to TextFileReader so
        # that it uses stdin. NOTE: we should really use a pattern that
        # echoes timestamp.DATE_FORMAT, e.g.
        # DATE_FORMAT_WILDCARD = '????-??-??'
        self.file_spec = filebase + '*' if filebase else None
        self.reader = TextFileReader(file_spec=self.file_spec,
                                     tail=tail,
                                     refresh_file_spec=refresh_file_spec,
                                     retry_interval=retry_interval,
                                     interval=interval)

    ############################
    def read(self):
        """
        Return the next line in the file(s), or None if there are no more
        records (as opposed to '' if the next record is a blank line). To test
        EOF you'll need to test

          if record is None:
            no more records...

        rather than simply

          if not record:
            could be EOF or simply an empty next line
        """

        # NOTE: It feels like we should check here that the reader's
        # current file really does match our logfile name format...
        while True:
            record = self.reader.read()
            if not record:  # None means we're out of records
                return None

            # If we've got a record and we're not using timestamps, we're
            # done - just return it.
            if not self.use_timestamps:
                self.prev_record = record
                # We need this in case the next call is seek_time() or
                # read_time_range(). This is less expensive than parsing every
                # timestamp and keeping self.last_timestamp, but an
                # alternative might be to implement read_previous(), which
                # would be expensive but which could be called only when
                # actually needed.
                return record

            # If we are using timestamps, make sure we can parse the
            # timestamp off the front. If we can't, complain and try getting
            # the next record.
            try:
                parsed_record = self.compiled_record_format.parse(record).named
                ts = parsed_record['timestamp'].timestamp()
                break

            # We had a problem parsing. Discard record and try reading next one.
            # Complain if appropriate.
            except (KeyError, ValueError, AttributeError):
                if not self.quiet:
                    logging.warning('Unable to parse record into "%s"', self.record_format)
                    logging.warning('Record: %s', record)
                continue

        # If here, we've got a record and a timestamp and are intending to
        # use it. Figure out how long we should sleep before returning it.
        desired_interval = ts - self.last_timestamp
        now = timestamp.timestamp()
        actual_interval = now - self.last_read
        logging.debug('Desired interval %f, actual %f; sleeping %f',
                      desired_interval, actual_interval,
                      max(0, desired_interval-actual_interval))
        time.sleep(max(0, desired_interval - actual_interval))

        self.last_timestamp = ts
        self.last_read = timestamp.timestamp()

        self.prev_record = record
        return record

    ############################
    def _read_until(self, desired_time_msec):
        while True:
            record = self.reader.read()
            if record is None:
                return
            self.prev_record = record
            if self._get_msec_timestamp(record) >= desired_time_msec:
                self.reader.seek(-1, 'current')
                return

    ############################
    def _reset(self):
        self.reader.seek(0, 'start')

    ############################
    def _get_msec_timestamp(self, record):
        time_str = record.split(' ', 1)[0]
        return timestamp.timestamp(time_str, time_format=self.time_format) * 1000

    ############################
    def _peek_msec(self):
        record = self.reader.read()
        if record is None:
            return None
        self.reader.seek(-1, 'current')
        return self._get_msec_timestamp(record)

    ############################
    # Note: this will change the file position if necessary, and should not be used
    # except where that behavior is appropriate.
    def _get_first_msec_timestamp(self):
        if self._first_msec_timestamp is None:
            self._reset()
            record = self.reader.read()
            if record is None:
                return None
            self._first_msec_timestamp = self._get_msec_timestamp(record)
        return self._first_msec_timestamp

    ############################
    def seek_time(self, offset=0, origin='current'):
        """
        Behavior is intended to mimic file seek() behavior but with
        respect to timestamps.
        After calling this, the next record read will be the first record
        whose timestamp is the same as or later than the requested time;
        if no such record is found, it will read to the end.
        Exception: if the records are not in exact chronological order,
        records appearing before the current record but with a later
        timestamp might be missed.

        Args:
          offset: offset in msec relative to origin
          origin: 'start', 'current' or 'end'

        Returns:
          Requested time in msec, i.e. timestamp of (T0 + offset),
          where T0 = timestamp(first record) if origin = 'start'
                   = timestamp(next record) if origin = 'current' and next record is not None
                   = timestamp(last record) if origin = 'current' and next record is None
                   = timestamp(last record) if origin = 'end'
          Returns None if no timestamps were found
        """
        if self.filebase is None:
            raise ValueError('seek_time() not allowed on stdin')

        # TODO: Maybe these are OK, as long as 'end' is defined as the point where
        # read() returns None for the first time.
        if self.tail and origin == 'end':
            raise ValueError('tail=True incompatible with origin == "end"')
        if self.refresh_file_spec and origin == 'end':
            raise ValueError('refresh_file_spec=True incompatible with origin == "end"')

        if origin == 'start':
            if offset < 0:
                raise ValueError("Can't back up past earliest record")
            first_timestamp = self._get_first_msec_timestamp()
            if first_timestamp is None:
                return None
            desired_time = first_timestamp + offset
            if self.prev_record is None:
                self._reset()
            else:
                prev_timestamp = self._get_msec_timestamp(self.prev_record)
                if prev_timestamp >= desired_time:
                    self._reset()
            self._read_until(desired_time)
            return desired_time

        elif origin == 'current':
            next_timestamp = self._peek_msec()
            curr_timestamp = next_timestamp or self._get_msec_timestamp(self.prev_record)
            if curr_timestamp is None:
                return None
            desired_time = curr_timestamp + offset
            if offset == 0:
                return desired_time
            if offset < 0:
                self._reset()
            self._read_until(desired_time)
            return desired_time

        elif origin == 'end':
            while self.read() is not None:
                pass
            if self.prev_record is None:
                return None
            end_timestamp = self._get_msec_timestamp(self.prev_record)
            desired_time = end_timestamp + offset
            if offset < 0:
                self._reset()
                self._read_until(desired_time)
            return desired_time

        else:
            raise ValueError('Unknown origin value: "%s"' % origin)

    ############################
    # Read a range of records beginning with timestamp start
    # milliseconds, and ending *before* timestamp stop milliseconds.
    def read_time_range(self, start=None, stop=None):
        if self.filebase is None:
            raise ValueError('read_time_range() not allowed on stdin')

        # TODO: Is this needed? stop=None would be OK unless records are
        # being written faster than they're being read.
        if stop is None:
            if self.tail:
                raise ValueError('tail=True incompatible with stop=None')
            if self.refresh_file_spec:
                raise ValueError('refresh_file_spec=True incompatible with stop=None')

        if start is None:
            starting_offset = 0
        else:
            starting_offset = start - self._get_first_msec_timestamp()

        self.seek_time(starting_offset, 'start')
        records = []
        while True:
            record = self.read()
            if record is None:
                break
            if stop and self._get_msec_timestamp(record) >= stop:
                break
            records.append(record)
        return records
