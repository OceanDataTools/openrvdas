#!/usr/bin/env python3

import logging
import sys
import tempfile
import time
import unittest
import warnings

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.text_file_reader import TextFileReader  # noqa: E402
from logger.transforms.prefix_transform import PrefixTransform  # noqa: E402
from logger.writers.text_file_writer import TextFileWriter  # noqa: E402
from logger.listener.listener import Listener  # noqa: E402

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


############################
def create_file(filename, lines, interval=0, pre_sleep_interval=0):
    time.sleep(pre_sleep_interval)
    logging.info('creating file "%s"', filename)
    with open(filename, 'w') as f:
        for line in lines:
            time.sleep(interval)
            f.write(line + '\n')
            f.flush()


################################################################################
class TestListener(unittest.TestCase):
    ############################
    # To suppress resource warnings about unclosed files
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmpdirname = self.tmpdir.name
        logging.info('created temporary directory "%s"', self.tmpdirname)

        self.tmpfilenames = []
        for f in sorted(SAMPLE_DATA):
            logging.debug('Creating sample file %s', f)
            tmpfilename = self.tmpdirname + '/' + f
            self.tmpfilenames.append(tmpfilename)
            create_file(tmpfilename, SAMPLE_DATA[f])

    ############################
    def test_check_format(self):

        # This should be okay - for now it warns us that check_format
        # is not implemented for ComposedWriter
        with self.assertLogs(logging.getLogger(), logging.WARNING):
            with self.assertRaises(ValueError):
                Listener([TextFileReader(self.tmpfilenames[0]),
                          TextFileReader(self.tmpfilenames[1])],
                         check_format=True)

        # No longer raises exception - only logs warning
        # This should not be - no common reader format
        # with self.assertRaises(ValueError):
        #  Listener([TextFileReader(self.tmpfilenames[0]), Reader()],
        #                 check_format=True)

    ############################
    def test_read_all_write_one(self):
        readers = []
        for tmpfilename in self.tmpfilenames:
            readers.append(TextFileReader(tmpfilename, interval=0.2))

        transforms = [PrefixTransform('prefix_1'),
                      PrefixTransform('prefix_2')]

        outfilename = self.tmpdirname + '/f_out'
        writers = [TextFileWriter(outfilename)]

        listener = Listener(readers, transforms, writers)
        listener.run()

        out_lines = []
        with open(outfilename, 'r') as f:
            for line in f.readlines():
                out_lines.append(line.rstrip())
        out_lines.sort()

        source_lines = []
        for f in SAMPLE_DATA:
            source_lines.extend(['prefix_2 prefix_1 ' + f for f in SAMPLE_DATA[f]])
        source_lines.sort()

        logging.debug('out: %s, source: %s', out_lines, source_lines)
        self.assertEqual(out_lines, source_lines)

    ############################

    def test_read_one_write_all(self):
        readers = TextFileReader(self.tmpfilenames[0])

        outfilenames = [self.tmpdirname + '/' + f
                        for f in ['f1_out', 'f2_out', 'f3_out']]
        writers = [TextFileWriter(ofn) for ofn in outfilenames]

        listener = Listener(readers=readers, writers=writers)
        listener.run()

        for ofn in outfilenames:
            line_num = 0
            with open(ofn, 'r') as f:
                for line in f.readlines():
                    self.assertEqual(SAMPLE_DATA['f1'][line_num], line.rstrip())
                    line_num += 1


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
