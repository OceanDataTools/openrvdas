#!/usr/bin/env python3

import logging
import sys
import tempfile
import time
import unittest
import warnings

from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.text_file_writer import TextFileWriter  # noqa: E402
from logger.writers.composed_writer import ComposedWriter  # noqa: E402
from logger.transforms.prefix_transform import PrefixTransform  # noqa: E402
from logger.transforms.parse_nmea_transform import ParseNMEATransform  # noqa: E402

SAMPLE_DATA = ['f1 line 1',
               'f1 line 2',
               'f1 line 3']


class TestComposedWriter(unittest.TestCase):

    ############################
    # To suppress resource warnings about unclosed files
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmpdirname = self.tmpdir.name
        logging.info('created temporary directory "%s"', self.tmpdirname)

    ############################
    def test_all_files(self):

        f1_name = self.tmpdirname + '/f1'
        f2_name = self.tmpdirname + '/f2'
        writer = ComposedWriter(transforms=[],
                                writers=[TextFileWriter(f1_name),
                                         TextFileWriter(f2_name)])

        f1 = open(f1_name, 'r')
        f2 = open(f2_name, 'r')

        for line in SAMPLE_DATA:
            writer.write(line)
            time.sleep(0.1)
            f1_line = f1.readline().rstrip()
            f2_line = f2.readline().rstrip()

            logging.info('wrote: "%s", f1: "%s", f2: "%s"', line, f1_line, f2_line)
            self.assertEqual(line, f1_line)
            self.assertEqual(line, f2_line)

    ############################
    def test_prefix(self):

        prefix_1 = PrefixTransform('p1')
        prefix_2 = PrefixTransform('p2')

        f1_name = self.tmpdirname + '/f1'
        f2_name = self.tmpdirname + '/f2'
        writer = ComposedWriter(transforms=[prefix_1, prefix_2],
                                writers=[TextFileWriter(f1_name),
                                         TextFileWriter(f2_name)])

        f1 = open(f1_name, 'r')
        f2 = open(f2_name, 'r')

        for line in SAMPLE_DATA:
            writer.write(line)
            time.sleep(0.1)
            f1_line = f1.readline().rstrip()
            f2_line = f2.readline().rstrip()

            logging.info('wrote: "%s", f1: "%s", f2: "%s"', line, f1_line, f2_line)
            self.assertEqual('p2 p1 ' + line, f1_line)
            self.assertEqual('p2 p1 ' + line, f2_line)


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
