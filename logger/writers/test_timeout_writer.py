#!/usr/bin/env python3

import logging
import sys
import tempfile
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.text_file_writer import TextFileWriter  # noqa: E402
from logger.writers.timeout_writer import TimeoutWriter  # noqa: E402


def create_file(filename, lines, interval=0, pre_sleep_interval=0):
    time.sleep(pre_sleep_interval)
    logging.info('creating file "%s"', filename)
    with open(filename, 'w') as f:
        for line in lines:
            time.sleep(interval)
            f.write(line + '\n')
            f.flush()


class TestTimeoutWriter(unittest.TestCase):
    ############################
    def test_basic(self):
        # Create a file
        temp_dir = tempfile.TemporaryDirectory()
        temp_dir_name = temp_dir.name
        test_file = temp_dir_name + '/test.txt'
        logging.info('creating temporary file "%s"', test_file)

        client_writer = TextFileWriter(filename=test_file)
        timeout_writer = TimeoutWriter(writer=client_writer, timeout=0.5,
                                       message='off', resume_message='on')

        time.sleep(0.75)  # trigger an "off" message
        timeout_writer.write('foo')  # trigger an "on" message
        time.sleep(1.2)  # should trigger just one "off" message

        timeout_writer.quit()

        # Now check the file - make sure we got
        with open(test_file, 'r') as f:
            lines = f.read().strip().split('\n')
            self.assertEqual(lines[0], 'off')
            self.assertEqual(lines[1], 'on')
            self.assertEqual(lines[2], 'off')
            self.assertEqual(len(lines), 3)


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
