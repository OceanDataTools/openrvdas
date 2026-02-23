#!/usr/bin/env python3

import os.path
import sys
import datetime
from typing import Union

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa E402
from logger.writers.writer import Writer  # noqa: E402


class TextFileWriter(Writer):
    """Write to the specified file. If filename is empty, write to stdout."""

    def __init__(self, filename=None, flush=True, truncate=False,
                 split_by_date=False, create_path=True, header=None,
                 header_file=None, **kwargs):
        """Write text records to a file. If no filename is specified, write to
        stdout.
        ```
        filename     Name of file to write to. If None, write to stdout

        flush        If True (default), flush after every write() call

        truncate     Truncate file before beginning to write

        split_by_date Create a separate text file for every day, appending
                     a -YYYY-MM-DD string to the specified filename.

        create_path  Create directory path to file if it doesn't exist

        header       Add the specified header string to each file.

        header_file  Add the content of the specified file to each file.
      ```
        """
        # Initialize type checking
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        self.filename = filename
        self.flush = flush
        self.truncate = truncate
        self.split_by_date = split_by_date
        self.header = None

        if split_by_date and not filename:
            raise ValueError('TextFileWriter: filename must be specified if '
                             'split_by_date is True.')

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
            except:  # noqa E722 - though should really fix this
                raise ValueError('FileWriter: Unable to add header to data '
                                 'file. header_file argument must be a valid '
                                 'filepath: %s', header_file)

        # If we're splitting by date, keep track of current file date
        # here.
        self.file_date = None
        self.file = None

        # If directory doesn't exist, try to create it
        if filename and create_path:
            file_dir = os.path.dirname(filename)
            if file_dir:
                os.makedirs(file_dir, exist_ok=True)

        # Figure out what file we ought be writing to and open it.
        self._set_file()

    ############################
    def _today(self):
        """Return a tuple for (year, month, day). Broken out into a separate
        function to facilitate testing."""
        now = datetime.datetime.utcnow()
        return (now.year, now.month, now.day)

    ############################
    def _set_file(self):
        """Make sure the right file is open. If we're splitting by date and
        the date has rolled over, close the old file and open a new
        one. This all feels overly convoluted, but is necessary to keep
        checking if we're splitting by date.
        """

        # If they haven't given us a filename, we'll write to stdout
        if self.filename is None:
            self.file = sys.stdout

            if self.header is not None:
                self.file.write(self.header)

            return

        # If here, we have a filename. Check if we're splitting by date;
        # if so, see if it's time to close out our current file an start a
        # new one.
        if self.split_by_date:
            today = self._today()
            if self.file_date != today:
                self.file_date = today
                if self.file:
                    self.file.close()
                    self.file = None

        # If we do have a file open, return.
        if self.file:
            return

        # If here, we don't have a file open. This may be because it's our
        # first time writing, or because we're splitting by dates and
        # we've rolled over to a new date.
        if self.split_by_date:
            today_str = '%04d-%02d-%02d' % self.file_date
            filename = '%s-%s' % (self.filename, today_str)
        else:
            filename = self.filename

        # Open and set the file
        mode = 'w' if self.truncate else 'a'
        self.file = open(filename, mode)

        # Add header record to file if a header was specified.
        if self.header is not None:
            self.file.write(self.header)

    ############################
    def write(self, record: Union[str, DASRecord]):
        """ Write out record, appending a newline at end."""

        if not self.can_process_record(record):  # inherited from BaseModule()
            self.digest_record(record)           # inherited from BaseModule()
            return

        if isinstance(record, DASRecord):
            record = record.as_json()

        # If we're splitting by date, make sure that we're still writing
        # to the right file.
        if self.split_by_date:
            self._set_file()

        # Write the record and flush if requested
        self.file.write(str(record) + '\n')
        if self.flush:
            self.file.flush()
