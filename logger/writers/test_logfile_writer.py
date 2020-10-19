#!/usr/bin/env python3

import logging
import sys
import tempfile
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.logfile_writer import LogfileWriter  # noqa: E402


SAMPLE_DATA = """2017-11-03T17:23:04.832875Z Nel mezzo del cammin di nostra vita
2017-11-03T17:23:04.833188Z mi ritrovai per una selva oscura,
2017-11-03T17:23:04.833243Z ché la diritta via era smarrita.
2017-11-04T17:23:04.833274Z Ahi quanto a dir qual era è cosa dura
2017-11-04T17:23:04.833303Z esta selva selvaggia e aspra e forte
2017-11-04T17:23:04.833330Z che nel pensier rinova la paura!
2017-11-05T17:23:04.833356Z Tant' è amara che poco è più morte;
2017-11-05T17:23:04.833391Z ma per trattar del ben ch'i' vi trovai,
2017-11-05T17:23:04.833418Z dirò de l'altre cose ch'i' v'ho scorte.
"""
SAMPLE_DATA_NO_TIMESTAMP = """Io non so ben ridir com' i' v'intrai,
' era pien di sonno a quel punto
che la verace via abbandonai.
"""


class TestLogfileWriter(unittest.TestCase):

    ############################
    def test_write(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            lines = SAMPLE_DATA.split('\n')

            filebase = tmpdirname + '/logfile'

            writer = LogfileWriter(filebase)

            with self.assertLogs(logging.getLogger(), logging.ERROR):
                writer.write('there is no timestamp here')

            r = range(0, 3)
            for i in r:
                writer.write(lines[i])
                time.sleep(0.25)

            with open(filebase + '-2017-11-03', 'r') as outfile:
                for i in r:
                    self.assertEqual(lines[i], outfile.readline().rstrip())

            r = range(3, 6)
            for i in r:
                writer.write(lines[i])

            with open(filebase + '-2017-11-04', 'r') as outfile:
                for i in r:
                    self.assertEqual(lines[i], outfile.readline().rstrip())

            r = range(6, 9)
            for i in r:
                writer.write(lines[i])

            with open(filebase + '-2017-11-05', 'r') as outfile:
                for i in r:
                    self.assertEqual(lines[i], outfile.readline().rstrip())


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
