#!/usr/bin/env python3

import logging
import sys
import tempfile
import time
import unittest

sys.path.append('.')
from logger.writers.text_file_writer import TextFileWriter  # noqa: E402

SAMPLE_DATA = ['f1 line 1',
               'f1 line 2',
               'f1 line 3']

SAMPLE_HEADER = 'Hi, I\'m a header'


############################
def create_file(filename, lines, interval=0, pre_sleep_interval=0):
    time.sleep(pre_sleep_interval)
    logging.info('creating file "%s"', filename)
    f = open(filename, 'w')
    for line in lines:
        time.sleep(interval)
        f.write(line + '\n')
        f.flush()
    f.close()


########################################################
class TodayTextFileWriter(TextFileWriter):
    """A hacked version of TextFileWriter where we can tweak what "today" is."""

    def __init__(self, filename=None, flush=True, truncate=False,
                 split_by_date=False, create_path=True):
        self.today = (2019, 9, 9)
        super().__init__(filename=filename, flush=flush, truncate=truncate,
                         split_by_date=split_by_date, create_path=create_path)

    ############################
    # Override _today() to return whatever we set it as
    def _today(self):
        """Manual version of _today()."""
        return self.today


########################################################
class TestTextFileWriter(unittest.TestCase):
    ############################
    def test_write(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = TextFileWriter(tmpdirname + '/f')
            f = open(tmpdirname + '/f')
            for line in SAMPLE_DATA:
                writer.write(line)
                self.assertEqual(line, f.readline().strip())

    ############################
    def test_write_with_header(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = TextFileWriter(tmpdirname + '/f', header=SAMPLE_HEADER)
            for line in SAMPLE_DATA:
                writer.write(line)

            with open(tmpdirname + '/f') as f:
                self.assertEqual(SAMPLE_HEADER, f.readline().strip())
                for line in SAMPLE_DATA:
                    self.assertEqual(line, f.readline().strip())

    ############################
    def test_compatible(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = TextFileWriter(tmpdirname + '/f')
            writer.write('str')  # Should not complain
            with self.assertLogs(logging.getLogger(), logging.WARNING):
                writer.write({1: 2})  # Should complain that can't write dicts

    ############################
    def test_split(self):
        """Test the split_by_date parameter, changing the date with each write."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = TodayTextFileWriter(tmpdirname + '/g', split_by_date=True)

            writer.today = (2019, 5, 1)
            writer.write(SAMPLE_DATA[0])
            with open(tmpdirname + '/g-%04d-%02d-%02d' % writer.today) as f:
                self.assertEqual(SAMPLE_DATA[0], f.readline().strip())

            writer.today = (2019, 5, 3)
            writer.write(SAMPLE_DATA[1])
            with open(tmpdirname + '/g-%04d-%02d-%02d' % writer.today) as f:
                self.assertEqual(SAMPLE_DATA[1], f.readline().strip())

            writer.today = (2019, 5, 9)
            writer.write(SAMPLE_DATA[2])
            with open(tmpdirname + '/g-%04d-%02d-%02d' % writer.today) as f:
                self.assertEqual(SAMPLE_DATA[2], f.readline().strip())


if __name__ == '__main__':
    unittest.main(warnings='ignore')
