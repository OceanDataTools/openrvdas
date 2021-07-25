#!/usr/bin/env python3

import logging
import shutil
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.formats import Python_Record  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402


class RecordScreenWriter(Writer):
    """Write DASRecords to terminal screen in some survivable
    format. Mostly intended for debugging."""

    def __init__(self):
        super().__init__(input_format=Python_Record)

        self.values = {}
        self.timestamps = {}
        self.latest = 0

    ############################
    def move_cursor(self, x, y):
        print('\033[{};{}f'.format(str(x), str(y)))

    ############################
    # receives a DASRecord
    def write(self, record):
        if not record:
            return

        # If we've got a list, hope it's a list of records. Recurse,
        # calling write() on each of the list elements in order.
        if isinstance(record, list):
            for single_record in record:
                self.write(single_record)
            return

        if not isinstance(record, DASRecord):
            logging.error('ScreenWriter got non-DASRecord: %s', str(type(record)))
            return

        # Incorporate the values from the record
        self.latest = record.timestamp
        for field in record.fields:
            self.values[field] = record.fields[field]
            self.timestamps[field] = self.latest

        # Get term size, in case it's been resized
        (cols, rows) = shutil.get_terminal_size()
        self.move_cursor(0, 0)
        # Redraw stuff
        keys = sorted(self.values.keys())
        for i in range(rows):
            # Go through keys in alpha order
            if i < len(keys):
                key = keys[i]
                line = '{} : {}'.format(key, self.values[key])

            # Fill the rest of the screen with blank lines
            else:
                line = ''

            # Pad the lines out to screen width to overwrite old stuff
            pad_size = cols - len(line)
            line += ' ' * pad_size

            print(line)
