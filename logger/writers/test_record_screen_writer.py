#!/usr/bin/env python3
"""Test that can be run manually to visually verify that the
ScreenWriter is doing what we think it should be doing. But it only
causes a mess if run as part of the test suite."""
import logging
import sys
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.nmea_parser import NMEAParser  # noqa: E402
from logger.writers.record_screen_writer import RecordScreenWriter  # noqa: E402

RECORDS = """
seap 2017-11-04T05:12:19.481328Z $GPZDA,235959.92,06,08,2014,,*65
seap 2017-11-04T05:12:19.735342Z $GPGGA,235959.92,3934.831152,S,03727.694551,W,1,11,0.9,-5.30,M,,M,,*6F  # noqa: E501
seap 2017-11-04T05:12:19.990659Z $GPVTG,226.69,T,,M,10.8,N,,K,A*23
seap 2017-11-04T05:12:20.245888Z $GPHDT,236.03,T*01
seap 2017-11-04T05:12:20.501188Z $PSXN,20,1,0,0,0*3A
seap 2017-11-04T05:12:20.754583Z $PSXN,22,0.44,0.81*30
seap 2017-11-04T05:12:21.006515Z $PSXN,23,-2.54,1.82,236.03,-1.67*34
seap 2017-11-04T05:12:21.261835Z $GPZDA,000000.92,07,08,2014,,*65
seap 2017-11-04T05:12:21.517092Z $GPGGA,000000.92,3934.833175,S,03727.697459,W,1,11,0.9,-5.89,M,,M,,*61  # noqa: E501
seap 2017-11-04T05:12:21.772426Z $GPVTG,229.63,T,,M,10.8,N,,K,A*26
seap 2017-11-04T05:12:22.022646Z $GPHDT,236.28,T*08
seap 2017-11-04T05:12:22.272874Z $PSXN,20,1,0,0,0*3A
seap 2017-11-04T05:12:22.526512Z $PSXN,22,0.44,0.81*30
seap 2017-11-04T05:12:22.779671Z $PSXN,23,-2.50,-1.48,236.28,-1.06*15
seap 2017-11-04T05:12:23.030096Z $GPZDA,000001.92,07,08,2014,,*64
seap 2017-11-04T05:12:23.281760Z $GPGGA,000001.92,3934.835118,S,03727.700517,W,1,11,0.9,-7.07,M,,M,,*6D  # noqa: E501
seap 2017-11-04T05:12:23.532669Z $GPVTG,231.79,T,,M,11.1,N,,K,A*2C
seap 2017-11-04T05:12:23.783004Z $GPHDT,236.56,T*01
seap 2017-11-04T05:12:24.035708Z $PSXN,20,1,0,0,0*3A
seap 2017-11-04T05:12:24.287940Z $PSXN,22,0.44,0.81*30
seap 2017-11-04T05:12:24.540765Z $PSXN,23,-2.19,-3.26,236.56,0.13*33
seap 2017-11-04T05:12:24.790998Z $GPZDA,000002.92,07,08,2014,,*67
seap 2017-11-04T05:12:25.046195Z $GPGGA,000002.92,3934.837038,S,03727.703725,W,1,11,0.9,-7.98,M,,M,,*69  # noqa: E501
seap 2017-11-04T05:12:25.301541Z $GPVTG,232.31,T,,M,11.5,N,,K,A*27
seap 2017-11-04T05:12:25.553129Z $GPHDT,236.47,T*01
seap 2017-11-04T05:12:25.806433Z $PSXN,20,1,0,0,0*3A
seap 2017-11-04T05:12:26.061721Z $PSXN,22,0.44,0.81*30
seap 2017-11-04T05:12:26.314857Z $PSXN,23,-1.63,-2.22,236.47,1.04*3F
seap 2017-11-04T05:12:26.567007Z $GPZDA,000003.92,07,08,2014,,*66
seap 2017-11-04T05:12:26.819311Z $GPGGA,000003.92,3934.839023,S,03727.706977,W,1,11,0.9,-7.98,M,,M,,*60  # noqa: E501
seap 2017-11-04T05:12:27.071958Z $GPVTG,230.75,T,,M,11.7,N,,K,A*27
seap 2017-11-04T05:12:27.327301Z $GPHDT,235.98,T*00
seap 2017-11-04T05:12:27.581758Z $PSXN,20,1,0,0,0*3A
seap 2017-11-04T05:12:27.832511Z $PSXN,22,0.44,0.81*30
seap 2017-11-04T05:12:28.085464Z $PSXN,23,-1.03,0.41,235.98,1.04*12
seap 2017-11-04T05:12:28.335724Z $GPZDA,000004.91,07,08,2014,,*62
seap 2017-11-04T05:12:28.586228Z $GPGGA,000004.91,3934.841042,S,03727.710114,W,1,10,0.9,-7.22,M,,M,,*66  # noqa: E501
seap 2017-11-04T05:12:28.837839Z $GPVTG,229.21,T,,M,11.4,N,,K,A*2D
seap 2017-11-04T05:12:29.091909Z $GPHDT,235.63,T*04
seap 2017-11-04T05:12:29.347263Z $PSXN,20,1,0,0,0*3A
seap 2017-11-04T05:12:29.602303Z $PSXN,22,0.44,0.81*30
seap 2017-11-04T05:12:29.852553Z $PSXN,23,-0.84,2.47,235.63,0.22*19
seap 2017-11-04T05:12:30.107463Z $GPZDA,000005.91,07,08,2014,,*63
seap 2017-11-04T05:12:30.362874Z $GPGGA,000005.91,3934.843045,S,03727.713132,W,1,11,0.9,-6.32,M,,M,,*64""".split('\n')  # noqa: E501


class TestRecordScreenWriter(unittest.TestCase):
    ############################
    @unittest.skipUnless(__name__ == '__main__',
                         'This test can be run manually to verify screen action '
                         'but will wreak havoc on the terminal if run as part of '
                         'a normal test suite.')
    def test_default_parser(self):
        p = NMEAParser()
        t = RecordScreenWriter()

        for line in RECORDS:
            record = p.parse_record(line)
            t.write(record)
            time.sleep(0.1)


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
