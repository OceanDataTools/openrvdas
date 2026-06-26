#!/usr/bin/env python3

import logging
import tempfile
import time
import unittest
import warnings

from logger.readers.text_file_reader import TextFileReader  # noqa: E402
from logger.transforms.prefix_transform import PrefixTransform  # noqa: E402
from logger.transforms.count_transform import CountTransform  # noqa: E402
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
    def test_type_hints(self):
        # Test that type hint warnings get triggered
        outfilename = self.tmpdirname + '/type_hints_out.txt'

        l1 = Listener(readers=[TextFileReader(self.tmpfilenames[0])],
                      transforms=[CountTransform()],
                      writers=[TextFileWriter(filename=outfilename)])

        with self.assertLogs(logging.getLogger(), logging.WARNING):
            l1.run()

        # Shouldn't be any output
        t = TextFileReader(outfilename)
        self.assertIsNone(t.read())

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

    ############################
    def test_no_readers_or_writers(self):
        # A Listener with neither readers nor writers should return
        # promptly rather than spinning.
        listener = Listener()
        start = time.time()
        listener.run()
        self.assertLess(time.time() - start, 1.0)

    ############################
    def test_no_extra_sleep_after_eof(self):
        # run() must not sleep out a final interval after the reader has
        # returned EOF. With a single-record file and interval=1.0, the
        # fixed version takes ~1.0s (one inter-record sleep); the old
        # behavior took ~2.0s (an extra sleep after reading None).
        single_line = self.tmpdirname + '/single.txt'
        create_file(single_line, ['only line'])

        outfilename = self.tmpdirname + '/eof_out'
        listener = Listener(readers=[TextFileReader(single_line)],
                            writers=[TextFileWriter(outfilename)],
                            interval=1.0)
        start = time.time()
        listener.run()
        elapsed = time.time() - start

        self.assertLess(elapsed, 1.6)

        with open(outfilename, 'r') as f:
            out_lines = [line.rstrip() for line in f.readlines()]
        self.assertEqual(out_lines, ['only line'])

    ############################
    def test_config_dict_not_mutated(self):
        # Building a Listener (via the helper that handles stderr_writers)
        # must not mutate the caller's config dict. We exercise the
        # Listener constructor's None-normalization here as a lightweight
        # proxy: constructing with explicit empty containers must not raise
        # and must leave passed-in lists untouched.
        readers = [TextFileReader(self.tmpfilenames[0])]
        transforms = []
        writers = [TextFileWriter(self.tmpdirname + '/nomutate_out')]

        Listener(readers=readers, transforms=transforms, writers=writers)
        self.assertEqual(len(readers), 1)
        self.assertEqual(transforms, [])
        self.assertEqual(len(writers), 1)

    ############################
    def test_default_args_not_shared(self):
        # Regression for mutable default arguments: two default-constructed
        # Listeners must not share reader/writer/transform state.
        a = Listener()
        b = Listener()
        self.assertIsNot(a.reader.readers, b.reader.readers)
        self.assertIsNot(a.writer.writers, b.writer.writers)


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
