#!/usr/bin/env python3

import logging
import io
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

sys.path.append('.')
from logger.writers.file_writer import FileWriter  # noqa: E402

SAMPLE_DATA = ['f1 line 1',
               'f1 line 2',
               'f1 line 3']

SAMPLE_HEADER = 'Hi, I\'m a header'


class TestFileWriter(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        self.writers_to_cleanup = []

    def tearDown(self):
        """Clean up any open file handles to avoid __del__ exceptions."""
        for writer in self.writers_to_cleanup:
            try:
                if hasattr(writer, 'file') and writer.file:
                    writer.file.close()
                    writer.file = None
            except:
                pass
        self.writers_to_cleanup.clear()

    def _cleanup_writer(self, writer):
        """Helper method to register a writer for cleanup."""
        self.writers_to_cleanup.append(writer)
        return writer

    ############################
    def test_write_stdout(self):
        buf = io.StringIO()
        with patch("sys.stdout", new=buf):
            writer = self._cleanup_writer(FileWriter(None))
            for line in SAMPLE_DATA:
                writer.write(line)

        # Get what was written to stdout
        output = buf.getvalue().splitlines()
        self.assertEqual(output, SAMPLE_DATA)

    ############################
    def test_write(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = self._cleanup_writer(FileWriter(tmpdirname + '/f'))
            for line in SAMPLE_DATA:
                writer.write(line)

            with open(tmpdirname + '/f') as f:
                for line in SAMPLE_DATA:
                    self.assertEqual(line, f.readline().strip())

    ############################
    def test_write_with_header(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = self._cleanup_writer(FileWriter(tmpdirname + '/f', header=SAMPLE_HEADER))
            for line in SAMPLE_DATA:
                writer.write(line)

            with open(tmpdirname + '/f') as f:
                self.assertEqual(SAMPLE_HEADER, f.readline().strip())
                for line in SAMPLE_DATA:
                    self.assertEqual(line, f.readline().strip())

    ############################
    def test_write_no_delimiter(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = self._cleanup_writer(FileWriter(tmpdirname + '/f', delimiter=None))
            for line in SAMPLE_DATA:
                writer.write(line)

            with open(tmpdirname + '/f') as f:
                self.assertEqual(f.readline(), ''.join(SAMPLE_DATA))

    ############################
    def test_split_day(self):
        """Test the split_interval parameter, changing the date with each write."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            writer = self._cleanup_writer(FileWriter(tmpdirname + '/g', split_interval='24H'))

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
            writer = self._cleanup_writer(FileWriter(tmpdirname + '/g', split_interval='1H',
                                                     date_format='-%Y-%m-%d:%H'))

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

    ############################
    def test_split_interval_configuration(self):
        """Test that split_interval parameter is properly configured."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            # Test hourly split configuration
            writer_h = self._cleanup_writer(FileWriter(tmpdirname + '/h', split_interval='2H'))

            # Verify proper configuration
            self.assertEqual(writer_h.split_interval, (2, 'H'))
            self.assertEqual(writer_h.split_interval_in_seconds, 2 * 3600)
            self.assertIn('%H', writer_h.date_format)

            # Test minute split configuration
            writer_m = self._cleanup_writer(FileWriter(tmpdirname + '/m', split_interval='15M'))

            # Verify proper configuration
            self.assertEqual(writer_m.split_interval, (15, 'M'))
            self.assertEqual(writer_m.split_interval_in_seconds, 15 * 60)
            self.assertIn('%H', writer_m.date_format)
            self.assertIn('%M', writer_m.date_format)

    ############################
    def test_split_interval_file_creation(self):
        """Test that split_interval creates files correctly."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            import os

            # Test that files are created with timestamp suffixes
            writer = self._cleanup_writer(FileWriter(tmpdirname + '/test', split_interval='1H'))

            # Write a record and verify file is created
            writer.write(SAMPLE_DATA[0])
            self.assertIsNotNone(writer.file)
            self.assertTrue(os.path.exists(writer.file.name))

            # Verify the filename has a timestamp suffix
            filename = writer.file.name
            self.assertTrue(filename.startswith(tmpdirname + '/test-'))

            # Verify content
            file_name = writer.file.name
            writer.file.close()
            writer.file = None

            with open(file_name) as f:
                content = f.read().strip()
                self.assertEqual(SAMPLE_DATA[0], content)

    ############################
    def test_split_interval_validation(self):
        """Test that split_interval parameter validation works correctly."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            # Test invalid format - no H or M suffix
            with self.assertRaises(ValueError) as context:
                FileWriter(tmpdirname + '/invalid1', split_interval='2X')
            self.assertIn('must be an integer followed by \'H\' or \'M\'', str(context.exception))

            # Test invalid format - non-integer prefix
            with self.assertRaises(ValueError) as context:
                FileWriter(tmpdirname + '/invalid2', split_interval='abcH')
            self.assertIn('must be an integer followed by \'H\' or \'M\'', str(context.exception))

            # Test that filename is required when using split_interval
            with self.assertRaises(ValueError) as context:
                FileWriter(filebase=None, split_interval='1H')
            self.assertIn('filebase must be specified', str(context.exception))

    ############################
    def test_split_interval_time_format_auto_update(self):
        """Test that date_format is automatically updated for split_interval."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            # Test that default date_format gets auto-updated for hourly splits
            writer_h = self._cleanup_writer(FileWriter(tmpdirname + '/test_h', split_interval='2H'))
            self.assertIn('%H', writer_h.date_format)
            self.assertIn('T', writer_h.date_format)

            # Test that default date_format gets auto-updated for minute splits
            writer_m = self._cleanup_writer(FileWriter(tmpdirname + '/test_m', split_interval='15M'))
            self.assertIn('%H', writer_m.date_format)
            self.assertIn('%M', writer_m.date_format)
            self.assertIn('T', writer_m.date_format)

            # Test that valid custom formats work
            writer_custom = self._cleanup_writer(FileWriter(tmpdirname + '/test_custom',
                                                            split_interval='1H',
                                                            date_format='-%Y-%m-%d_%H'))
            self.assertEqual(writer_custom.date_format, '-%Y-%m-%d_%H')


    ############################
    def test_date_format_validation(self):
        """Test that date_format is verified against what's required for the
        split_interval."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            with self.assertRaises(ValueError) as context:
                FileWriter(tmpdirname + '/invalid1', split_interval='24H', date_format='-%Y-%m')
            self.assertIn('date_format must include %m, %d (month, day) or %j (day-of-year).', str(context.exception))

            # Test invalid format - no %H in date_format
            with self.assertRaises(ValueError) as context:
                FileWriter(tmpdirname + '/invalid1', split_interval='2H', date_format='-%Y-%m-%d')
            self.assertIn('date_format must include %H (hour).', str(context.exception))

            # Test invalid format - no %H in date_format
            with self.assertRaises(ValueError) as context:
                FileWriter(tmpdirname + '/invalid1', split_interval='15M', date_format='-%Y-%m-%dT%H')
            self.assertIn('date_format must include %M (minute).', str(context.exception))


################################################################################
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
