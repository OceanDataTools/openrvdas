#!/usr/bin/env python3

import logging
import sys
import tempfile
import threading
import unittest
import warnings
from datetime import datetime

sys.path.append('.')
from logger.utils.simulate_data import SimSerial  # noqa: E402
from logger.transforms.slice_transform import SliceTransform  # noqa: E402
# from logger.readers.serial_reader import SerialReader  # noqa: E402
from contrib.whoi.logger.readers.serial_reader import SerialReader, LOGGING_TIME_FORMAT  # noqa: E402

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

SAMPLE_MAX_BYTES_2 = ['$H',
                      'EH',
                      'DT',
                      ',2',
                      '34',
                      '.7',
                      '6,',
                      'T*',
                      '1b']

SAMPLE_TIMEOUT = ['$HEHDT,234.76,T*1b',
                  None,
                  None,
                  '$HEHDT,234.73,T*1e',
                  None,
                  None,
                  '$HEHDT,234.72,T*1f',
                  None,
                  None,
                  '$HEHDT,234.72,T*1f',
                  None,
                  None,
                  '$HEHDT,234.73,T*1e']

PREFIX = 'SSW'
SENSOR = 'SBE48'


################################################################################
class TestSerialReader(unittest.TestCase):


    ############################
    # utility to match WHOI-format timestamps
    @staticmethod
    def is_valid_timestamp(date_str, time_str, fmt=LOGGING_TIME_FORMAT):
        try:
            datetime.strptime(f'{date_str} {time_str}', fmt)
            return True
        except ValueError:
            return False

    ############################
    # Set up config file and sample logfile to feed simulated serial port
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

        # Set up config file and logfile simulated serial port will read from
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmpdirname = self.tmpdir.name
        logging.info('created temporary directory "%s"', self.tmpdirname)

        self.port = self.tmpdirname + '/tty_gyr1'
        self.logfile_filename = self.tmpdirname + '/NBP1700_gyr1-2017-11-04'
        with open(self.logfile_filename, 'w') as f:
            f.write(SAMPLE_DATA)

    ############################
    # When max_bytes is not specified, SerialReader should read port up
    # to a newline character.
    def test_readline(self):
        port = self.port + '_readline'
        sim = SimSerial(port=port, filebase=self.logfile_filename)
        sim_thread = threading.Thread(target=sim.run)
        sim_thread.start()

        slice = SliceTransform('1:')  # we'll want to strip out timestamp

        # Then read from serial port
        s = SerialReader(port, prefix=PREFIX)
        for line in SAMPLE_DATA.split('\n'):
            data = slice.transform(line)
            record = s.read()
            logging.debug('data: %s, read: %s', data, record)

            prefix, date_str, time_str, remainder = record.split(' ', 3)
            self.assertEqual(prefix, PREFIX)
            self.assertTrue(self.is_valid_timestamp(date_str, time_str))
            self.assertEqual(data, remainder)

    ############################
    # When max_bytes is not specified, SerialReader should read port up
    # to a newline character.
    def test_readline_with_sensor(self):
        port = self.port + '_readline'
        sim = SimSerial(port=port, filebase=self.logfile_filename)
        sim_thread = threading.Thread(target=sim.run)
        sim_thread.start()

        slice = SliceTransform('1:')  # we'll want to strip out timestamp

        # Then read from serial port
        s = SerialReader(port, prefix=PREFIX, sensor=SENSOR)
        for line in SAMPLE_DATA.split('\n'):
            data = slice.transform(line)
            record = s.read()
            logging.debug('data: %s, read: %s', data, record)

            prefix, date_str, time_str, sensor, remainder = record.split(' ', 4)
            self.assertEqual(prefix, PREFIX)
            self.assertTrue(self.is_valid_timestamp(date_str, time_str))
            self.assertEqual(sensor, SENSOR)
            self.assertEqual(data, remainder)

    ############################
    # When max_bytes specified, read up to that many bytes each time.
    def test_read_bytes(self):
        port = self.port + '_read_bytes'
        sim = SimSerial(port=port, filebase=self.logfile_filename)
        sim_thread = threading.Thread(target=sim.run)
        sim_thread.start()

        # Then read from serial port
        s = SerialReader(port=port, max_bytes=2, prefix=PREFIX)
        for data in SAMPLE_MAX_BYTES_2:
            record = s.read()
            logging.debug('data: %s, read: %s', data, record)

            prefix, date_str, time_str, remainder = record.split(' ', 3)
            self.assertEqual(prefix, PREFIX)
            self.assertTrue(self.is_valid_timestamp(date_str, time_str))
            self.assertEqual(data, remainder)

    ############################
    # For unicode craziness
    def test_unicode(self):
        port = self.port + '_unicode'
        sim = SimSerial(port=port, filebase=self.logfile_filename)
        sim_thread = threading.Thread(target=sim.run)
        sim_thread.start()

        # For some reason, the test complains unless we actually read
        # from the port. This first SerialReader is here just to get
        # rid of the error message that pops up from SimSerial if we
        # don't use it.
        s = SerialReader(port=port, prefix=PREFIX)
        s.read()

        # Now we're going to create SerialReaders with stubbed
        # self.serial.readline methods so that when they're called,
        # we instead get the same bit of bad unicode over and over
        # again. We want to test that it performs correctly under
        # conditions.

        # A dummy serial readline that will feed us bad unicode
        def dummy_readline():
            return b'\xe2\x99\xa5\x99\xe2\x99\xa5\x00\xe2\x99\xa5\xe2\x99\xa5'

        # Create a SerialReader, then replace its serial reader with a stub so
        # we can feed it bad records.

        s = SerialReader(port=port, prefix=PREFIX)
        s.serial.readline = dummy_readline

        prefix, date_str, time_str, remainder = s.read().split(' ', 3)
        self.assertEqual(prefix, PREFIX)
        self.assertTrue(self.is_valid_timestamp(date_str, time_str))
        self.assertEqual('♥♥\x00♥♥', remainder)

        s = SerialReader(port=port, encoding_errors='replace', prefix=PREFIX)
        s.serial.readline = dummy_readline

        prefix, date_str, time_str, remainder = s.read().split(' ', 3)
        self.assertEqual(prefix, PREFIX)
        self.assertTrue(self.is_valid_timestamp(date_str, time_str))
        self.assertEqual('♥�♥\x00♥♥', remainder)

    ############################
    # When timeout specified...
    def test_timeout(self):
        port = self.port + '_timeout'
        sim = SimSerial(port=port, filebase=self.logfile_filename)
        sim_thread = threading.Thread(target=sim.run)
        sim_thread.start()

        # Then read from serial port
        s = SerialReader(port=port, timeout=0.1, prefix=PREFIX)
        for line in SAMPLE_TIMEOUT:
            record = s.read()
            logging.debug('data: %s, read: %s', line, record)

            prefix, date_str, time_str, remainder = record.split(' ', 3)

            self.assertEqual(prefix, PREFIX)
            self.assertTrue(self.is_valid_timestamp(date_str, time_str))

            if remainder == '':
                remainder = None

            self.assertEqual(line, remainder, msg='Note: this is a time-sensitive '
                             'test that can fail non-deterministically. If the '
                             'test fails, try running from the command line, e.g. '
                             'as "logger/readers/test_serial_reader.py"')


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

    # unittest.main(warnings='ignore')
    unittest.main()
