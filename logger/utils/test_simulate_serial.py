#!/usr/bin/env python3

import logging
import sys
import tempfile
import time
import threading
import unittest
import warnings

try:
    import serial
except ModuleNotFoundError:
    raise ModuleNotFoundError('Missing module "serial". Install with "pip3 '
                              'install pyserial"')

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.slice_transform import SliceTransform  # noqa: E402
from logger.utils.simulate_serial import SimSerial  # noqa: E402


PORT = '%DIR%/tty_gyr1'

SAMPLE_CONFIG = """{
    "gyr1": {"port": "%DIR%/tty_gyr1",
             "logfile": "%DIR%/NBP1700_gyr1"
            }
}
"""

SAMPLE_DATA = """2017-11-04T05:12:19.275337Z $HEHDT,234.76,T*1b
2017-11-04T05:12:19.527360Z $HEHDT,234.73,T*1e
2017-11-04T05:12:19.781738Z $HEHDT,234.72,T*1f
2017-11-04T05:12:20.035450Z $HEHDT,234.72,T*1f
2017-11-04T05:12:20.286551Z $HEHDT,234.73,T*1e
2017-11-04T05:12:20.541843Z $HEHDT,234.76,T*1b
2017-11-04T05:12:20.796684Z $HEHDT,234.81,T*13
2017-11-04T05:12:21.047098Z $HEHDT,234.92,T*11
2017-11-04T05:12:21.302371Z $HEHDT,235.06,T*1d
2017-11-04T05:12:21.557630Z $HEHDT,235.22,T*1b
2017-11-04T05:12:21.809445Z $HEHDT,235.38,T*10
2017-11-04T05:12:22.062809Z $HEHDT,235.53,T*1d
2017-11-04T05:12:22.312971Z $HEHDT,235.66,T*1b"""

################################################################################


class TestSimulateSerial(unittest.TestCase):

    ############################
    # To suppress resource warnings about unclosed files
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

        # Set up config file and logfile simulated serial port will read from
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmpdirname = self.tmpdir.name
        logging.info('created temporary directory "%s"', self.tmpdirname)

        self.config_filename = self.tmpdirname + '/gyr.config'
        self.logfile_filename = self.tmpdirname + '/NBP1700_gyr1-2017-11-04'

        with open(self.config_filename, 'w') as f:
            config_str = SAMPLE_CONFIG.replace('%DIR%', self.tmpdirname)
            f.write(config_str)
        with open(self.logfile_filename, 'w') as f:
            f.write(SAMPLE_DATA)

    ############################
    def test_use_timestamps(self):
        port = PORT.replace('%DIR%', self.tmpdirname)
        sim = SimSerial(port=port, source_file=self.logfile_filename)
        sim_thread = threading.Thread(target=sim.run)
        sim_thread.start()

        # Give it a moment to get started
        time.sleep(0.1)

        slice = SliceTransform('1:')  # we'll want to strip out timestamp

        # Then read from serial port
        s = serial.Serial(port=port)
        last_read = time.time() - 0.15
        for line in SAMPLE_DATA.split('\n'):
            data = slice.transform(line)
            record = s.readline().strip().decode('utf-8')
            now = time.time()
            logging.debug('time diff %f', now - last_read)
            self.assertAlmostEqual(now - last_read, 0.26, places=1)
            self.assertEqual(data, record)
            last_read = now

    ############################
    def test_fast(self):
        port = PORT.replace('%DIR%', self.tmpdirname)
        sim = SimSerial(port=port, source_file=self.logfile_filename,
                        use_timestamps=False)
        sim_thread = threading.Thread(target=sim.run)
        sim_thread.start()

        # Give it a moment to get started
        time.sleep(0.1)

        slice = SliceTransform('1:')  # we'll want to strip out timestamp

        # Then read from serial port
        s = serial.Serial(port=port)
        last_read = time.time() + 0.1
        for line in SAMPLE_DATA.split('\n'):
            data = slice.transform(line)
            record = s.readline().strip().decode('utf-8')
            now = time.time()
            logging.debug('time diff %f', now - last_read)
            self.assertLess(now - last_read, 0.02)
            self.assertEqual(data, record)
            last_read = now


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

    # unittest.main(warnings='ignore')
    unittest.main()
