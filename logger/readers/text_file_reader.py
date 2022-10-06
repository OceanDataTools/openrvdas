#!/usr/bin/env python3

import glob
import logging
import sys
import time

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.formats import Text  # noqa: E402
from logger.readers.reader import StorageReader  # noqa: E402


################################################################################
# Open and read single-line records from one or more text files.
class TextFileReader(StorageReader):
    """Read lines from one or more text files. Sequentially open all
    files that match the file_spec.
    """
    ############################

    def __init__(self, file_spec=None, tail=False, refresh_file_spec=False,
                 retry_interval=0.1, interval=0, eol=None):
        """
        ```
        file_spec    Possibly wildcarded string speficying files to be opened.
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

        eol          Optional character by which to recognize the end of a record
        ```
        Note that the order in which files are opened will probably be in
        alphanumeric by filename, but this is not strictly enforced and
        depends on how glob returns them.
        """

        super().__init__(output_format=Text)

        self.file_spec = file_spec
        self.tail = tail
        self.refresh_file_spec = refresh_file_spec
        self.retry_interval = retry_interval
        self.interval = interval
        self.eol = eol

        # If interval != 0, we need to keep track of our last_read to know
        # how long to sleep
        self.last_read = 0

        # The file we're currently using
        self.current_file = None

        self.pos = 0
        self.start_pos = {}
        self.end_pos = {}

        # Special case if file_spec is None
        if file_spec is None:
            self.current_file = sys.stdin
            self.used_file_list = []
            self.unused_file_list = []
            self.tail = True
            return

        # Which files will we use, which haven't we used yet?
        self.unused_file_list = sorted(glob.glob(file_spec))
        if not self.unused_file_list:
            logging.warning('TextFileReader: file_spec "%s" matches no files',
                            file_spec)
        self.used_file_list = []

    ############################

    def _get_next_file(self):
        """Internal - Open and assign the next unused file to
        self.current_file if we can find one. Return None (and don't mess
        with current_file) if we can't find a next one.
        """
        # If no more unused files, but refresh_file_spec is specified, see
        # if more files have shown up
        if not self.unused_file_list and self.refresh_file_spec:
            matching_files = sorted(glob.glob(self.file_spec))
            self.unused_file_list = [f for f in matching_files
                                     if f not in self.used_file_list]
            logging.info('TextFileReader found %d new files matching spec "%s": %s',
                         len(self.unused_file_list), self.file_spec,
                         self.unused_file_list)

        # Are there any more files? If so, get the next one and open it
        if self.unused_file_list:
            # First, save the record count for the file we're about to close.
            if self.used_file_list:
                prev_filename = self.used_file_list[-1]
                self.end_pos[prev_filename] = self.pos

            next_filename = self.unused_file_list.pop(0)
            logging.info('TextFileReader opening next file "%s"', next_filename)
            self.start_pos[next_filename] = self.pos
            self.current_file = open(next_filename, 'r')
            self.used_file_list.append(next_filename)
            return self.current_file

        # If here, we've found no unused next file. Give up
        return None

    ############################
    def read(self):
        """Get the next line of text. Return None if there are no more
        records.  To test EOF you'll need to test

          if record is None:
            no more records...

        rather than simply

          if not record:
            could be EOF or simply an empty next line
        """
        if self.interval:
            now = time.time()
            sleep_time = max(0, self.interval - (now - self.last_read))
            logging.debug('Sleeping %f seconds', sleep_time)
            if sleep_time:
                time.sleep(sleep_time)

        record = None
        while not record:
            # If we've got a current file, or if _get_next_file() gets one
            # for us, try to read a record.
            if self.current_file or self._get_next_file():
                if not self.eol:
                    record = self.current_file.readline()
                else:
                    record = self._read_until_eol()
                if record:
                    self.last_read = time.time()
                    record = record.rstrip('\n')
                    logging.debug('TextFileReader got record "%s"', record)
                    self.pos += 1
                    return record

                # No record: our current_file has reached EOF. See if more
                # files we should try to read.
                if self._get_next_file():
                    # Found a new file to read - loop again right away
                    continue

            # EOF when we're reading from stdin means we're done
            if not self.file_spec:
                return None

            # No record, no new files, no tail or refresh directive -
            # there's nothing left for us to try. Go home empty-handed.
            if not self.refresh_file_spec and not self.tail:
                return None

            # User wants refresh or tail, so sleep and try again.
            logging.debug('TextFileReader - tail/refresh specified, so sleeping '
                          '%f seconds before trying again', self.retry_interval)
            time.sleep(self.retry_interval)

    ############################
    # If self.eol is a string instead of None, read until we've consumed that
    # string or reached eof, and return that as a record.
    def _read_until_eol(self):
        if not self.eol:
            logging.fatal('Code error: called _read_until_eof, but no eof string specified')
            return

        record = ''
        eol_index = 0  # we're going to count our way through eol characters
        while eol_index < len(self.eol):
            # read by character
            char = self.current_file.read(1)
            if char == '':
                break
            elif char == self.eol[eol_index]:
                eol_index += 1
                record += char
            else:
                eol_index = 0
                record += char

        # If we're here because we did in fact get a full eol string,
        # retroactively snip it from our record.
        if eol_index == len(self.eol):
            record = record[:-eol_index]

        return record

    ############################
    # Current behavior is to just go to the end if we run out of records,
    # as io.IOBase.seek() does.
    # QUESTION: To really behave like seek(), we'd have to keep track of self.pos
    # beyond the end of the file, e.g. seek(100, 'start') would always return
    # 100, even if there are < 100 records. Is this what we want?
    def _seek_forward_from_current(self, offset=0):
        if offset == 0:
            return
        if offset < 0:
            return self._seek_back_from_current(offset)
        i = 0
        while i < offset:
            if self.current_file or self._get_next_file():
                if self.current_file.readline():
                    i += 1
                    self.pos += 1
                else:
                    if self._get_next_file() is None:
                        break
        # TODO: take advantage of self.start_pos and self.end_pos if we've
        # already processed later files.

    ############################
    def _seek_back_from_current(self, offset=0):
        if offset == 0:
            return
        if offset > 0:
            return self._seek_forward_from_current(offset)
        target = self.pos + offset
        if target < 0:
            raise ValueError("Can't back up past earliest record")

        # Find the right file.
        current_filename = self.used_file_list[-1]
        while target < self.start_pos[current_filename]:
            self.unused_file_list.insert(0, current_filename)
            self.used_file_list.pop()
            current_filename = self.used_file_list[-1]

        self.current_file = open(current_filename, 'r')

        # TODO: implement backwards search within the file
        for _ in range(target - self.start_pos[current_filename]):
            self.current_file.readline()
        self.pos = target

    ############################
    def _save_state(self):
        state = {
            'used_file_list': self.used_file_list[:],
            'unused_file_list': self.unused_file_list[:],
            'pos': self.pos
        }
        if self.current_file:
            state['current_filename'] = self.used_file_list[-1]
            state['current_file_pos'] = self.current_file.tell()
        return state

    ############################
    def _restore_state(self, state):
        self.used_file_list = state['used_file_list']
        self.unused_file_list = state['unused_file_list']
        if 'current_filename' in state:
            self.current_file = open(state['current_filename'], 'r')
            self.current_file.seek(state['current_file_pos'])
        else:
            self.current_file = None
        self.pos = state['pos']

    ############################
    # Behavior is intended to mimic file seek() behavior but with
    # respect to records: 'offset' means number of records, and origin
    # is either 'start', 'current' or 'end'.
    def seek(self, offset=0, origin='current'):
        original_state = self._save_state()

        try:
            if origin == 'start':
                if offset < 0:
                    raise ValueError("Can't back up past earliest record")
                self.used_file_list = []
                self.unused_file_list = sorted(glob.glob(self.file_spec))
                self.current_file = None
                self.pos = 0
                self._seek_forward_from_current(offset)

            elif origin == 'current':
                if offset >= 0:
                    self._seek_forward_from_current(offset)
                else:
                    self._seek_back_from_current(offset)

            elif origin == 'end':
                # Have to count lines in all files that haven't been processed yet.
                # TODO: take self.refresh_file_spec into account
                file_list = sorted(glob.glob(self.file_spec))
                pos = 0
                for filename in file_list:
                    if filename in self.end_pos:
                        pos = self.end_pos[filename]
                    else:
                        self.start_pos[filename] = pos

                        # TODO: this can be made faster, if needed
                        with open(filename) as f:
                            for n, _ in enumerate(f, 1):
                                pass

                        pos += n
                        self.end_pos[filename] = pos

                self.used_file_list = file_list
                self.unused_file_list = []
                self.current_file = None
                self.pos = pos
                self._seek_back_from_current(offset)

            else:
                raise ValueError('Unknown origin value: "%s"' % origin)

        except:  # noqa: E722
            self._restore_state(original_state)
            raise

        return self.pos

    ############################
    def read_range(self, start=None, stop=None):
        """
        Read a range of records beginning with record number start, and ending
        *before* record number stop.
        """
        if start is None:
            start = 0
        if stop is None:
            stop = sys.maxsize
        self.seek(start, 'start')
        records = []
        for _ in range(stop - start):
            record = self.read()
            if record is None:
                break
            records.append(record)
        return records
