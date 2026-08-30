#!/usr/bin/env python3

import logging
import os
import tempfile
import time
import unittest
import warnings

from logger.readers.text_file_reader import TextFileReader  # noqa: E402
from logger.writers.text_file_writer import TextFileWriter  # noqa: E402
from server.logger_runner import LoggerRunner  # noqa: E402

CONFIG = {
    "name": "logger",
    "readers": {
        "class": "TextFileReader",
        "kwargs": {
            "interval": 0.01,
            "tail": True
        }  # we'll fill in filespec once we have tmpdir
    },
    "writers": {
        "class": "TextFileWriter",
        "kwargs": {}  # we'll fill in filespec once we have tmpdir
    }
}

SAMPLE_DATA = """Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation files
(the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell...""".split('\n')


################################################################################
class TestLoggerRunnerStderrPath(unittest.TestCase):
    """LoggerRunner has to create the directory its stderr file lives in.

    Per-logger stderr defaults to /var/log/openrvdas/loggers/, which the
    installer creates - but an install upgraded without re-running it, or a
    custom --stderr_file_pattern, can point somewhere that doesn't exist. The
    handler is opened with delay=True, so a missing directory would not fail
    at construction: it would fail on the first write, where logging swallows
    the error and the stderr line is simply lost.
    """

    ############################
    def test_creates_missing_stderr_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stderr_file = os.path.join(tmpdir, 'loggers', 'gyr1.stderr')
            self.assertFalse(os.path.exists(os.path.dirname(stderr_file)))

            runner = LoggerRunner(config=CONFIG, name='gyr1',
                                  stderr_filename=stderr_file)
            self.assertTrue(os.path.isdir(os.path.dirname(stderr_file)),
                            'LoggerRunner should have created the directory')

            # And the handler can actually write there.
            runner.stderr_file_handler.emit(
                logging.LogRecord('gyr1', logging.INFO, '', 0,
                                  'a line of stderr', None, None))
            runner.stderr_file_handler.close()
            with open(stderr_file) as f:
                self.assertIn('a line of stderr', f.read())

    ############################
    def test_nested_missing_directories(self):
        """Several levels deep, as a non-default pattern might be."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stderr_file = os.path.join(tmpdir, 'a', 'b', 'c', 's330.stderr')
            LoggerRunner(config=CONFIG, name='s330',
                         stderr_filename=stderr_file)
            self.assertTrue(os.path.isdir(os.path.dirname(stderr_file)))

    ############################
    def test_existing_directory_is_left_alone(self):
        """An existing directory, and anything in it, must survive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stderr_dir = os.path.join(tmpdir, 'loggers')
            os.makedirs(stderr_dir)
            keeper = os.path.join(stderr_dir, 'previous.stderr')
            with open(keeper, 'w') as f:
                f.write('earlier output\n')

            LoggerRunner(config=CONFIG, name='gyr1',
                         stderr_filename=os.path.join(stderr_dir, 'gyr1.stderr'))
            self.assertTrue(os.path.exists(keeper))
            with open(keeper) as f:
                self.assertEqual(f.read(), 'earlier output\n')


################################################################################
class TestLoggerRunner(unittest.TestCase):
    ############################
    def setUp(self):
        # To suppress resource warnings about unclosed files
        warnings.simplefilter("ignore", ResourceWarning)

        # Create a file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_dir_name = self.temp_dir.name

        self.source_name = self.temp_dir_name + '/source.txt'
        self.dest_name = self.temp_dir_name + '/dest.txt'
        self.stderr_name = self.temp_dir_name + '/logger.stderr'

        # Create the source file
        writer = TextFileWriter(self.source_name)
        for line in SAMPLE_DATA:
            writer.write(line)

        self.config = CONFIG
        self.config['readers']['kwargs']['file_spec'] = self.source_name
        self.config['writers']['kwargs']['filename'] = self.dest_name

    ############################
    def _wait_for(self, condition, timeout=15):
        """Wait until condition() returns True, or fail."""
        end_time = time.time() + timeout
        while time.time() < end_time:
            if condition():
                return
            time.sleep(0.1)
        self.fail('Timed out waiting for condition')

    ############################
    def _dest_line_count(self):
        if not os.path.exists(self.dest_name):
            return 0
        with open(self.dest_name) as f:
            return len(f.readlines())

    ############################
    def test_basic(self):

        # Assure ourselves that the dest file doesn't exist yet
        self.assertFalse(os.path.exists(self.dest_name))

        runner = LoggerRunner(config=self.config)
        runner.start()

        # Wait for the logger subprocess to boot and copy all lines over
        self._wait_for(lambda: self._dest_line_count() >= len(SAMPLE_DATA))

        reader = TextFileReader(self.dest_name)
        for line in SAMPLE_DATA:
            result = reader.read()
            logging.info('Checking line: "%s"', line)
            logging.info('Against line:  "%s"', result)
            self.assertEqual(line, result)

        self.assertTrue(runner.is_runnable())
        self.assertTrue(runner.is_alive())
        self.assertFalse(runner.is_failed())

        runner.quit()
        self.assertFalse(runner.is_alive())

        # Try a degenerate runner; it shouldn't even start a process
        runner = LoggerRunner(config={})
        runner.start()

        self.assertFalse(runner.is_runnable())
        self.assertFalse(runner.is_alive())
        self.assertFalse(runner.is_failed())
        runner.quit()

    ############################
    def test_stderr_capture(self):
        """The runner should capture a failing logger's stderr and deliver
        it to both the stderr file and the callback - even though the
        process is already dead by the time we look."""
        bad_config = {
            'name': 'bad_logger',
            'readers': {
                'class': 'NoSuchReaderClass',
                'kwargs': {}
            },
            'writers': {
                'class': 'TextFileWriter',
                'kwargs': {'filename': self.dest_name}
            }
        }
        callback_lines = []
        runner = LoggerRunner(config=bad_config,
                              name='bad_logger',
                              stderr_filename=self.stderr_name,
                              stderr_callback=callback_lines.append)
        runner.start()

        # Process should die on its own, complaining as it goes
        self._wait_for(lambda: not runner.is_alive())

        # The relay should deliver the complaint to both destinations,
        # despite the process being dead.
        self._wait_for(lambda: len(callback_lines) > 0)
        self._wait_for(lambda: os.path.exists(self.stderr_name)
                       and os.path.getsize(self.stderr_name) > 0)

        stderr_text = '\n'.join(callback_lines)
        self.assertIn('NoSuchReaderClass', stderr_text)
        with open(self.stderr_name) as f:
            self.assertIn('NoSuchReaderClass', f.read())

        runner.quit()


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    # logging.getLogger().setLevel(logging.DEBUG)
    unittest.main(warnings='ignore')
