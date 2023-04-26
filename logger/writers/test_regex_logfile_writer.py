#!/usr/bin/env python3

import logging
import sys
import tempfile
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.regex_logfile_writer import RegexLogfileWriter  # noqa: E402

SAMPLE_DATA = """2017-11-03T17:23:04.832875Z AAA Nel mezzo del cammin di nostra vita
2017-11-03T17:23:04.833188Z BBB mi ritrovai per una selva oscura,
2017-11-03T17:23:04.833243Z CCC ché la diritta via era smarrita.
2017-11-04T17:23:04.833274Z BBB Ahi quanto a dir qual era è cosa dura
2017-11-04T17:23:04.833303Z AAA esta selva selvaggia e aspra e forte
2017-11-04T17:23:04.833330Z BBB CCC che nel pensier rinova la paura!
2017-11-04T17:23:05.833356Z CCC Tant' è amara che poco è più morte;
2017-11-04T17:23:06.833391Z AAA CCC ma per trattar del ben ch'i' vi trovai,
2017-11-04T17:23:07.833418Z BBB dirò de l'altre cose ch'i' v'ho scorte.
"""
SAMPLE_DATA_NO_TIMESTAMP = """Io non so ben ridir com' i' v'intrai,
' era pien di sonno a quel punto
che la verace via abbandonai.
"""

class TestRegexLogfileWriter(unittest.TestCase):
    ############################
    def test_write(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            lines = SAMPLE_DATA.split('\n')

            filebase = tmpdirname + '/logfile'

            writer = RegexLogfileWriter(filebase)

            with self.assertLogs(logging.getLogger(), logging.ERROR):
                writer.write('there is no timestamp here')

            r = range(0, 3)
            for i in r:
                writer.write(lines[i])

            with open(filebase + '-2017-11-03', 'r') as outfile:
                for i in r:
                    self.assertEqual(lines[i], outfile.readline().rstrip())

            r = range(3, 9)
            for i in r:
                writer.write(lines[i])

            with open(filebase + '-2017-11-04', 'r') as outfile:
                for i in r:
                    self.assertEqual(lines[i], outfile.readline().rstrip())

    ############################
    def test_map_write(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            lines = SAMPLE_DATA.split('\n')

            filebase = {
                'AAA': tmpdirname + '/logfile_A',
                'BBB': tmpdirname + '/logfile_B',
                'CCC': tmpdirname + '/logfile_C',
            }
            writer = RegexLogfileWriter(filebase=filebase)

            bad_line = 'there is no timestamp here'
            with self.assertLogs(logging.getLogger(), logging.ERROR) as cm:
                writer.write(bad_line)
            error = 'ERROR:root:LogfileWriter.write() - bad timestamp: ' + bad_line
            self.assertEqual(cm.output, [error])

            for line in lines:
                writer.write(line)

            #logging.warning(f'Tempdirname: {tmpdirname}')
            #time.sleep(200)

            with open(tmpdirname +'/logfile_A-2017-11-03', 'r') as outfile:
                self.assertEqual(lines[0], outfile.readline().rstrip())
                self.assertEqual('', outfile.readline().rstrip())

            with open(tmpdirname +'/logfile_A-2017-11-04', 'r') as outfile:
                self.assertEqual(lines[4], outfile.readline().rstrip())
                self.assertEqual(lines[7], outfile.readline().rstrip())
                self.assertEqual('', outfile.readline().rstrip())

            with open(tmpdirname +'/logfile_B-2017-11-03', 'r') as outfile:
                self.assertEqual(lines[1], outfile.readline().rstrip())
                self.assertEqual('', outfile.readline().rstrip())
            with open(tmpdirname +'/logfile_B-2017-11-04', 'r') as outfile:
                self.assertEqual(lines[3], outfile.readline().rstrip())
                self.assertEqual(lines[5], outfile.readline().rstrip())
                self.assertEqual(lines[8], outfile.readline().rstrip())
                self.assertEqual('', outfile.readline().rstrip())

            with open(tmpdirname +'/logfile_C-2017-11-03', 'r') as outfile:
                self.assertEqual(lines[2], outfile.readline().rstrip())
                self.assertEqual('', outfile.readline().rstrip())
            with open(tmpdirname +'/logfile_C-2017-11-04', 'r') as outfile:
                self.assertEqual(lines[5], outfile.readline().rstrip())
                self.assertEqual(lines[6], outfile.readline().rstrip())
                self.assertEqual(lines[7], outfile.readline().rstrip())
                self.assertEqual('', outfile.readline().rstrip())


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

    unittest.main(warnings='ignore')
