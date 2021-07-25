#!/usr/bin/env python3

import logging
import sys
import tempfile
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.timeout_reader import TimeoutReader  # noqa: E402
from logger.readers.text_file_reader import TextFileReader  # noqa: E402

SAMPLE_DATA = """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell...""".split('\n')

SAMPLE_SPACE_DATA = """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal



in the Software without restriction, including without limitation the rights""".split('\n')


################################################################################
def create_file(filename, lines, interval=0, pre_sleep_interval=0):
    time.sleep(pre_sleep_interval)
    logging.info('creating file "%s"', filename)
    with open(filename, 'w') as f:
        for line in lines:
            time.sleep(interval)
            f.write(line + '\n')
            f.flush()


################################################################################
class TestTimeoutReader(unittest.TestCase):
    ############################
    def test_basic(self):

        # Create a file
        temp_dir = tempfile.TemporaryDirectory()
        temp_dir_name = temp_dir.name
        test_file = temp_dir_name + '/test.txt'
        logging.info('creating temporary file "%s"', test_file)
        create_file(test_file, SAMPLE_DATA)

        # Create a reader to read it at 0.5 second intervals
        reader = TextFileReader(test_file, interval=0.5, tail=True)

        timeout_reader = TimeoutReader(reader, timeout=1, message='Timeout')

        # Our reader should do fine until it runs out of records after 2 seconds
        start_time = time.time()
        record = timeout_reader.read()
        end_time = time.time()
        self.assertEqual(record, 'Timeout')
        self.assertAlmostEqual(end_time - start_time, 2.5, delta=0.3)

        logging.info('Got timeout record "%s" after %g seconds',
                     record, end_time - start_time)

    ############################
    # Data with empty records
    def test_empty_lines(self):

        # Create a file
        temp_dir = tempfile.TemporaryDirectory()
        temp_dir_name = temp_dir.name
        test_file = temp_dir_name + '/test.txt'
        logging.info('creating temporary file "%s"', test_file)
        create_file(test_file, SAMPLE_SPACE_DATA)

        # Create a reader to read it at 0.5 second intervals
        reader = TextFileReader(test_file, interval=0.5, tail=True)
        timeout_reader = TimeoutReader(reader, timeout=1, message='Space Timeout')

        # Our reader should do fine until it hits the blank lines after 1.5 seconds
        start_time = time.time()
        record = timeout_reader.read()
        end_time = time.time()
        self.assertEqual(record, 'Space Timeout')
        self.assertAlmostEqual(end_time - start_time, 1.5, delta=0.3)

        logging.info('Got timeout record "%s" after %g seconds',
                     record, end_time - start_time)

    ############################
    # Data with empty records, but empty_is_okay flag
    def test_empty_lines_okay(self):

        # Create a file
        temp_dir = tempfile.TemporaryDirectory()
        temp_dir_name = temp_dir.name
        test_file = temp_dir_name + '/test.txt'
        logging.info('creating temporary file "%s"', test_file)
        create_file(test_file, SAMPLE_SPACE_DATA)

        # Create a reader to read it at 0.5 second intervals
        reader = TextFileReader(test_file, interval=0.5, tail=True)
        timeout_reader = TimeoutReader(reader, timeout=1, empty_is_okay=True,
                                       message='Space Timeout')

        # Our reader should do fine until it gets to the very end after 4 seconds
        start_time = time.time()
        record = timeout_reader.read()
        end_time = time.time()
        self.assertEqual(record, 'Space Timeout')
        self.assertAlmostEqual(end_time - start_time, 3.5, delta=0.3)

        logging.info('Got timeout record "%s" after %g seconds',
                     record, end_time - start_time)


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
