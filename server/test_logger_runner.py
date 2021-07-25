#!/usr/bin/env python3

import logging
import os
import sys
import tempfile
import time
import unittest
import warnings

from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))
from logger.readers.text_file_reader import TextFileReader  # noqa: E402
from logger.writers.text_file_writer import TextFileWriter  # noqa: E402
from server.logger_runner import LoggerRunner  # noqa: E402

CONFIG = {
    "name": "logger",
    "readers": {
        "class": "TextFileReader",
        "kwargs": {
            "interval": 0.1,
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

        # Create the source file
        writer = TextFileWriter(self.source_name)
        for line in SAMPLE_DATA:
            writer.write(line)

        self.config = CONFIG
        self.config['readers']['kwargs']['file_spec'] = self.source_name
        self.config['writers']['kwargs']['filename'] = self.dest_name

    ############################
    def test_basic(self):

        # Assure ourselves that the dest file doesn't exist yet and that
        # we're in our default mode
        self.assertFalse(os.path.exists(self.dest_name))

        runner = LoggerRunner(config=self.config)
        runner.start()
        time.sleep(1.0)

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

        # Try a degenerate runner
        runner = LoggerRunner(config={})
        runner.start()
        time.sleep(1.0)

        self.assertFalse(runner.is_runnable())
        self.assertFalse(runner.is_alive())
        self.assertFalse(runner.is_failed())


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
