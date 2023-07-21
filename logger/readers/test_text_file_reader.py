#!/usr/bin/env python3

import logging
import sys
import tempfile
import threading
import time
import unittest
import warnings

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.readers.text_file_reader import TextFileReader  # noqa: E402

SAMPLE_DATA = {
    'f1': ['f1 line 1',
           'f1 line 2',
           'f1 line 3'],
    'f2': ['f2 line 1',
           'f2 line 2',
           'f2 line 3'],
    'f3': ['f3 line 1',
           'f3 line 2',
           'f3 line 3']
}


def create_file(filename, lines, interval=0, pre_sleep_interval=0):
    time.sleep(pre_sleep_interval)
    logging.info('creating file "%s"', filename)
    f = open(filename, 'w')
    for line in lines:
        time.sleep(interval)
        f.write(line + '\n')
        f.flush()
    f.close()


class TestTextFileReader(unittest.TestCase):
    ############################
    # To suppress resource warnings about unclosed files
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    ############################
    def test_all_files(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            expected_lines = []
            for f in sorted(SAMPLE_DATA):
                create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
                expected_lines.extend(SAMPLE_DATA[f])

            reader = TextFileReader(tmpdirname + '/f*')
            for line in expected_lines:
                self.assertEqual(line, reader.read())
            self.assertEqual(None, reader.read())

    ############################
    def test_tail_false(self):
        # Don't specify 'tail' and expect there to be no data
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)

            # Create a file slowly, one line at a time
            target = 'f1'
            tmpfilename = tmpdirname + '/' + target
            threading.Thread(target=create_file,
                             args=(tmpfilename, SAMPLE_DATA[target], 0.25)).start()

            time.sleep(0.05)  # let the thread get started

            # Read, and wait for lines to come
            reader = TextFileReader(tmpfilename, tail=False)
            self.assertEqual(None, reader.read())

    ############################
    def test_tail_true(self):
        # Do the same thing as test_tail_false, but specify tail=True. We should
        # now get all the lines that are eventually written to the file.
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)

            # Create a file slowly, one line at a time
            target = 'f1'
            tmpfilename = tmpdirname + '/' + target
            threading.Thread(target=create_file,
                             args=(tmpfilename, SAMPLE_DATA[target], 0.25)).start()

            time.sleep(0.05)  # let the thread get started

            # Read, and wait for lines to come
            reader = TextFileReader(tmpfilename, tail=True)
            for line in SAMPLE_DATA[target]:
                self.assertEqual(line, reader.read())

    ############################
    def test_refresh_file_spec(self):
        # Delay creation of the file, but tell reader to keep checking for
        # new files.
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)

            # Create a file slowly, one line at a time, and delay even
            # creating the file so that when our TextFileReader starts, its
            # file_spec matches nothing.
            target = 'f1'
            tmpfilename = tmpdirname + '/' + target
            threading.Thread(target=create_file,
                             args=(tmpfilename, SAMPLE_DATA[target],
                                   0.25, 0.5)).start()

            time.sleep(0.05)  # let the thread get started

            with self.assertLogs(logging.getLogger(), logging.WARNING):
                reader = TextFileReader(tmpfilename, refresh_file_spec=True)
            for line in SAMPLE_DATA[target]:
                self.assertEqual(line, reader.read())

    ############################
    # Check that reader output_formats work the way we expect
    def test_formats(self):
        reader = TextFileReader(file_spec=None)

        self.assertEqual(reader.output_format(), formats.Text)
        self.assertEqual(reader.output_format(formats.NMEA), formats.NMEA)
        self.assertEqual(reader.output_format(), formats.NMEA)

        with self.assertRaises(TypeError):
            reader.output_format('not a format')

    ############################
    # Check some simple cases, forward movement only.
    def test_seek_forward(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            expected_lines = []
            for f in sorted(SAMPLE_DATA):
                create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
                expected_lines.extend(SAMPLE_DATA[f])

            reader = TextFileReader(tmpdirname + '/f*')

            self.assertEqual(2, reader.seek(2, 'start'))
            self.assertEqual(expected_lines[2], reader.read())
            self.assertEqual(expected_lines[3], reader.read())
            self.assertEqual(9, reader.seek(0, 'end'))
            self.assertEqual(None, reader.read())
            self.assertEqual(1, reader.seek(1, 'start'))
            self.assertEqual(expected_lines[1], reader.read())
            self.assertEqual(3, reader.seek(1, 'current'))
            self.assertEqual(expected_lines[3], reader.read())
            self.assertEqual(4, reader.seek(0, 'current'))
            self.assertEqual(expected_lines[4], reader.read())
            self.assertEqual(7, reader.seek(2, 'current'))
            self.assertEqual(expected_lines[7], reader.read())
            self.assertEqual(expected_lines[8], reader.read())
            self.assertEqual(None, reader.read())

    ############################
    # Check special cases for origin.
    def test_seek_origin(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            expected_lines = []
            for f in sorted(SAMPLE_DATA):
                create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
                expected_lines.extend(SAMPLE_DATA[f])

            reader = TextFileReader(tmpdirname + '/f*')

            with self.assertRaises(ValueError):
                reader.seek(0, 'xyz')

            # Move to middle of file (so current position isn't start or end).
            reader.seek(4, 'start')

            # Check that seek with no origin is relative to the current location.
            self.assertEqual(6, reader.seek(2))
            self.assertEqual(expected_lines[6], reader.read())

    ############################
    # Check seek with offset < 0 and origin = 'current'
    def test_seek_current_negative_offset(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            expected_lines = []
            for f in sorted(SAMPLE_DATA):
                create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
                expected_lines.extend(SAMPLE_DATA[f])

            reader = TextFileReader(tmpdirname + '/f*')

            for i in range(5):
                reader.read()

            self.assertEqual(3, reader.seek(-2, 'current'))
            self.assertEqual(expected_lines[3], reader.read())

            # Now try a bigger offset, so we have to go back a couple files.
            reader.seek(8, 'start')
            self.assertEqual(2, reader.seek(-6, 'current'))
            self.assertEqual(expected_lines[2], reader.read())

    ############################
    # Check seek with offset < 0 and origin = 'end'
    def test_seek_end_negative_offset(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            expected_lines = []
            for f in sorted(SAMPLE_DATA):
                create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
                expected_lines.extend(SAMPLE_DATA[f])

            reader = TextFileReader(tmpdirname + '/f*')

            self.assertEqual(7, reader.seek(-2, 'end'))
            self.assertEqual(expected_lines[7], reader.read())
            self.assertEqual(9, reader.seek(0, 'end'))
            self.assertEqual(None, reader.read())

            # Now try a bigger offset, so we have to go back a couple files.
            self.assertEqual(2, reader.seek(-7, 'end'))
            self.assertEqual(expected_lines[2], reader.read())

    ############################
    # Check that seek with negative offset larger than current position
    # results in a ValueError.
    def test_seek_before_beginning(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            expected_lines = []
            for f in sorted(SAMPLE_DATA):
                create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
                expected_lines.extend(SAMPLE_DATA[f])

            reader = TextFileReader(tmpdirname + '/f*')

            with self.assertRaises(ValueError):
                reader.seek(-1, 'current')

            with self.assertRaises(ValueError):
                reader.seek(-10, 'end')

            # check seek still works for in-bounds value
            self.assertEqual(2, reader.seek(-7, 'end'))
            self.assertEqual(expected_lines[2], reader.read())

    ############################
    # Check that after an error due to a seek beyond the beginning,
    # the state is unchanged, i.e. read() returns the record it would
    # have before the seek.
    def test_seek_position_unchanged_after_error(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            expected_lines = []
            for f in sorted(SAMPLE_DATA):
                create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
                expected_lines.extend(SAMPLE_DATA[f])

            reader = TextFileReader(tmpdirname + '/f*')

            reader.seek(5, 'start')
            with self.assertRaises(ValueError):
                reader.seek(-8, 'current')
            self.assertEqual(expected_lines[5], reader.read())

            reader.seek(2, 'start')
            with self.assertRaises(ValueError):
                reader.seek(-1, 'start')
            self.assertEqual(expected_lines[2], reader.read())

            reader.seek(7, 'start')
            with self.assertRaises(ValueError):
                reader.seek(-10, 'end')
            self.assertEqual(expected_lines[7], reader.read())

    ############################
    # Check a sequence of seeks of different types.
    def test_seek_multiple(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            expected_lines = []
            for f in sorted(SAMPLE_DATA):
                create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
                expected_lines.extend(SAMPLE_DATA[f])

            reader = TextFileReader(tmpdirname + '/f*')

            self.assertEqual(8, reader.seek(8, 'start'))
            self.assertEqual(expected_lines[8], reader.read())
            self.assertEqual(5, reader.seek(-4, 'current'))
            self.assertEqual(expected_lines[5], reader.read())
            self.assertEqual(7, reader.seek(-2, 'end'))
            self.assertEqual(expected_lines[7], reader.read())
            self.assertEqual(expected_lines[8], reader.read())
            self.assertEqual(None, reader.read())
            self.assertEqual(2, reader.seek(-7, 'end'))
            self.assertEqual(expected_lines[2], reader.read())
            self.assertEqual(8, reader.seek(5, 'current'))
            self.assertEqual(expected_lines[8], reader.read())

    ############################
    # Check that read_range() returns the expected list of records
    # for various values of start and stop.
    def test_read_range(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            expected_lines = []
            for f in sorted(SAMPLE_DATA):
                create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
                expected_lines.extend(SAMPLE_DATA[f])

            reader = TextFileReader(tmpdirname + '/f*')

            self.assertEqual(expected_lines[1:4], reader.read_range(1, 4))
            self.assertEqual(expected_lines[0:9], reader.read_range(0, 9))
            self.assertEqual(expected_lines[2:3], reader.read_range(start=2, stop=3))
            self.assertEqual(expected_lines[2:], reader.read_range(start=2))
            self.assertEqual(expected_lines[:3], reader.read_range(stop=3))
            self.assertEqual(expected_lines[2:], reader.read_range(start=2, stop=40))

    ############################
    # Check that after calling read_range(), the next read() returns
    # the first record after the range.
    def test_position_after_read_range(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            expected_lines = []
            for f in sorted(SAMPLE_DATA):
                create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
                expected_lines.extend(SAMPLE_DATA[f])

            reader = TextFileReader(tmpdirname + '/f*')

            reader.read_range(1, 6)
            self.assertEqual(expected_lines[6], reader.read())

            reader.read_range(0, 4)
            self.assertEqual(expected_lines[4], reader.read())

            reader.read_range(7, 9)
            self.assertEqual(None, reader.read())

    ############################
    # Check that after reading some records, read_range() still works.
    def test_read_range_after_read(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            expected_lines = []
            for f in sorted(SAMPLE_DATA):
                create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
                expected_lines.extend(SAMPLE_DATA[f])

            reader = TextFileReader(tmpdirname + '/f*')

            for i in range(5):
                reader.read()

            self.assertEqual(expected_lines[1:4], reader.read_range(1, 4))

    ############################
    def test_eol(self):
        # Check that we can recognize single and multiple eol char strings
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)

            # Create a file slowly, one line at a time
            target = 'f1'
            tmpfilename = tmpdirname + '/' + target
            create_file(tmpfilename, SAMPLE_DATA[target])

            # Read, and wait for lines to come
            for eol in ['e', 'ne', '\n']:
                reader = TextFileReader(tmpfilename, eol=eol)
                expect = '\n'.join(SAMPLE_DATA[target]).split(eol)
                for i in range(len(expect)):
                    line = reader.read()
                    self.assertEqual(line, expect[i])

if __name__ == '__main__':
    unittest.main()
