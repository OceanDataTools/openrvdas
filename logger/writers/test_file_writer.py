#!/usr/bin/env python3

import sys
import tempfile
import unittest


from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.file_writer import FileWriter  # noqa: E402

SAMPLE_DATA = ['f1 line 1',
               'f1 line 2',
               'f1 line 3']

SAMPLE_HEADER = 'Hi, I\'m a header'

class TestFileWriter(unittest.TestCase):

    ############################
    def test_write(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = FileWriter(tmpdirname + '/f')
            for line in SAMPLE_DATA:
                writer.write(line)

            with open(tmpdirname + '/f') as f:
                for line in SAMPLE_DATA:
                    self.assertEqual(line, f.readline().strip())

    ############################
    def test_write_with_header(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = FileWriter(tmpdirname + '/f', header=SAMPLE_HEADER)
            for line in SAMPLE_DATA:
                writer.write(line)

            with open(tmpdirname + '/f') as f:
                self.assertEqual(SAMPLE_HEADER, f.readline().strip())
                for line in SAMPLE_DATA:
                    self.assertEqual(line, f.readline().strip())

    ############################
    def test_write_no_delimiter(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = FileWriter(tmpdirname + '/f', delimiter=None)
            for line in SAMPLE_DATA:
                writer.write(line)

            with open(tmpdirname + '/f') as f:
                self.assertEqual(f.readline(), ''.join(SAMPLE_DATA))

    ############################
    def test_split_day(self):
        """Test the split_by_date parameter, changing the date with each write."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = FileWriter(tmpdirname + '/g', split_by_time=True)

            writer.timestamp = 1597150898
            writer.write(SAMPLE_DATA[0])

            writer.timestamp += 86400
            writer.write(SAMPLE_DATA[1])

            writer.timestamp += 86400
            writer.write(SAMPLE_DATA[2])

            with open(tmpdirname + '/g-2020-08-11') as f:
                self.assertEqual(SAMPLE_DATA[0], f.readline().strip())
            with open(tmpdirname + '/g-2020-08-12') as f:
                self.assertEqual(SAMPLE_DATA[1], f.readline().strip())
            with open(tmpdirname + '/g-2020-08-13') as f:
                self.assertEqual(SAMPLE_DATA[2], f.readline().strip())

    ############################
    def test_split_hour(self):
        """Test the split_by_date parameter, changing the date with each write."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = FileWriter(tmpdirname + '/g', split_by_time=True,
                                time_format='-%Y-%m-%d:%H')

            writer.timestamp = 1597150898
            writer.write(SAMPLE_DATA[0])

            writer.timestamp += 3600
            writer.write(SAMPLE_DATA[1])

            writer.timestamp += 3600
            writer.write(SAMPLE_DATA[2])

            with open(tmpdirname + '/g-2020-08-11:13') as f:
                self.assertEqual(SAMPLE_DATA[0], f.readline().strip())
            with open(tmpdirname + '/g-2020-08-11:14') as f:
                self.assertEqual(SAMPLE_DATA[1], f.readline().strip())
            with open(tmpdirname + '/g-2020-08-11:15') as f:
                self.assertEqual(SAMPLE_DATA[2], f.readline().strip())


if __name__ == '__main__':
    unittest.main(warnings='ignore')
