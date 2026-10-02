#!/usr/bin/env python3

import logging
import tempfile
import threading
import unittest
import warnings

from logger.utils.simulate_data import SimSerial  # noqa: E402
from logger.transforms.slice_transform import SliceTransform  # noqa: E402
from logger.readers.serial_reader import SerialReader  # noqa: E402

import serial  # noqa: E402

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


################################################################################
class TestSerialReader(unittest.TestCase):

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
        s = SerialReader(port)
        for line in SAMPLE_DATA.split('\n'):
            data = slice.transform(line)
            record = s.read()
            logging.debug('data: %s, read: %s', data, record)
            self.assertEqual(data, record)

    ############################
    # When max_bytes specified, read up to that many bytes each time.
    def test_read_bytes(self):
        port = self.port + '_read_bytes'
        sim = SimSerial(port=port, filebase=self.logfile_filename)
        sim_thread = threading.Thread(target=sim.run)
        sim_thread.start()

        # Then read from serial port
        s = SerialReader(port=port, max_bytes=2)
        for data in SAMPLE_MAX_BYTES_2:
            record = s.read()
            logging.debug('data: %s, read: %s', data, record)
            self.assertEqual(data, record)

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
        s = SerialReader(port=port)
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

        # These readers each stub out readline immediately and never take
        # data off the real port, so they don't need exclusive access to it -
        # and can't have it, since the reader above still holds the port.
        s = SerialReader(port=port, exclusive=False)
        s.serial.readline = dummy_readline
        self.assertEqual('♥♥\x00♥♥', s.read())

        s = SerialReader(port=port, encoding_errors='replace', exclusive=False)
        s.serial.readline = dummy_readline
        self.assertEqual('♥�♥\x00♥♥', s.read())

        s = SerialReader(port=port, encoding_errors='strict', exclusive=False)
        s.serial.readline = dummy_readline
        with self.assertLogs(logging.getLogger(), logging.WARNING):
            self.assertEqual(None, s.read())

        # Don't decode at all - return raw bytes
        s = SerialReader(port=port, encoding=None, exclusive=False)
        s.serial.readline = dummy_readline
        self.assertEqual(dummy_readline(), s.read())

        ############################
    # When timeout specified...
    def test_timeout(self):
        port = self.port + '_timeout'
        sim = SimSerial(port=port, filebase=self.logfile_filename)
        sim_thread = threading.Thread(target=sim.run)
        sim_thread.start()

        # Then read from serial port
        s = SerialReader(port=port, timeout=0.1)
        for line in SAMPLE_TIMEOUT:
            record = s.read()
            logging.debug('data: %s, read: %s', line, record)
            self.assertEqual(line, record, msg='Note: this is a time-sensitive '
                             'test that can fail non-deterministically. If the '
                             'test fails, try running from the command line, e.g. '
                             'as "logger/readers/test_serial_reader.py"')

    ############################
    # A second reader on the same port must fail rather than quietly splitting
    # the byte stream with the first one. See issue #641.
    def test_exclusive_by_default(self):
        port = self.port + '_exclusive_default'
        # SimSerial creates the pty and symlink in its constructor, so we
        # don't need to start its thread for a locking test - but we do need
        # to hold the reference, because its __del__ unlinks the port.
        sim = SimSerial(port=port, filebase=self.logfile_filename)  # noqa: F841

        first = SerialReader(port)
        try:
            with self.assertRaises(serial.SerialException) as cm:
                SerialReader(port)
            # The message should name the port and point at the cause, rather
            # than leaving the operator to decode pyserial's wording.
            message = str(cm.exception)
            self.assertIn(port, message)
            self.assertIn('locked by another process', message)
        finally:
            first.serial.close()

    ############################
    # ...but sharing is still available for anyone who genuinely wants it.
    def test_exclusive_false_allows_sharing(self):
        port = self.port + '_exclusive_false'
        sim = SimSerial(port=port, filebase=self.logfile_filename)  # noqa: F841

        first = SerialReader(port, exclusive=False)
        try:
            second = SerialReader(port, exclusive=False)
            second.serial.close()
        finally:
            first.serial.close()

    ############################
    # The lock is advisory (pyserial uses flock), so it only excludes
    # processes that also ask for it. Pin that down, because it bounds what
    # the exclusive default can promise: it stops a second OpenRVDAS logger,
    # not a stray 'cat' or 'minicom'.
    def test_lock_is_advisory(self):
        port = self.port + '_advisory'
        sim = SimSerial(port=port, filebase=self.logfile_filename)  # noqa: F841

        locked = SerialReader(port)  # exclusive=True by default
        try:
            unlocked = SerialReader(port, exclusive=False)
            unlocked.serial.close()
        finally:
            locked.serial.close()


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
