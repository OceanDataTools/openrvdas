#!/usr/bin/env python3

import logging
import sys
import tempfile
import time
import threading
import unittest
import warnings

sys.path.append('.')
from logger.readers.serial_reader import SerialReader  # noqa: E402
from logger.utils.simulate_data import SimSerial  # noqa: E402
from logger.writers.serial_writer import SerialWriter  # noqa: E402

SAMPLE_DATA = """2017-11-04T05:12:19.275337Z $HEHDT,234.76,T*1b
2017-11-04T05:12:19.527360Z $HEHDT,234.73,T*1e
2017-11-04T05:12:19.781738Z $HEHDT,234.72,T*1f
2017-11-04T05:12:20.035450Z $HEHDT,234.72,T*1f
2017-11-04T05:12:22.312971Z $HEHDT,235.66,T*1b"""

SPECIAL_STRING = '♥�♥\x00♥♥'

BINARY_DATA = [b'\xff\xa1',
               b'\xff\xa2',
               b'\xff\xa3']

SAMPLE_MAX_BYTES_2 = ['$H',
                      'EH',
                      'DT',
                      ',2',
                      '34',
                      '.7',
                      '6,',
                      'T*',
                      '1b']

SAMPLE_TIMEOUT = [None,
                  '$HEHDT,234.76,T*1b',
                  None, None,
                  '$HEHDT,234.73,T*1e',
                  None, None,
                  '$HEHDT,234.72,T*1f',
                  None, None,
                  '$HEHDT,234.72,T*1f',
                  None, None]


################################################################################
class TestSerialWriter(unittest.TestCase):
    ############################
    # Set up set up simulated serial in/out ports
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

        # Set up simulated in/out serial ports
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmpdirname = self.tmpdir.name
        logging.info('created temporary directory "%s"', self.tmpdirname)

        # Temp fake port. SimSerial expects a log file that it's going to read from.
        # We're never going to actually call SimSerial's run method, so the contents
        # of the file don't matter.
        self.tmp_port_name = self.tmpdirname + '/serial'
        self.dummy_filebase = self.tmpdirname + '/empty.txt'
        with open(self.dummy_filebase, 'w') as dummy_file:
            dummy_file.write('this file isn\'t used')

        # Create fake serial port. We'll write to sim_serial.write_port and read from
        # sim_serial.read_port
        # self.sim_serial = SimSerial(port=self.tmp_port_name, filebase=self.dummy_filebase)

    def _run_reader(self, port):
        logging.info(f'started _run_reader on port {port}')
        reader = SerialReader(port, baudrate=9600)
        for line in SAMPLE_DATA.split('\n'):
            result = reader.read()
            logging.info('data: %s, read: %s', line, result)
            self.assertEqual(line, result)

    def _run_read_specialcase(self, port):
        reader = SerialReader(port, eol="FOO\\n")
        res = reader.read()
        logging.info('data: %s, read: %s', SPECIAL_STRING, res)
        self.assertEqual(SPECIAL_STRING, res)

    def _run_read_binary(self, port):
        reader = SerialReader(port, encoding=None)
        for line in BINARY_DATA:
            result = reader.read()
            logging.info('data: %s, read %s', line, result)
            self.assertEqual(line, result)

    ############################
    # Test a couple cases and the quiet flag
    def test_write(self):
        sim_serial = SimSerial(port=self.tmp_port_name, filebase=self.dummy_filebase)

        write_port = sim_serial.write_port
        read_port = sim_serial.read_port

        # Give it a moment to get started
        time.sleep(0.1)

        def _run_writer():
            logging.info(f'started _run_writer on port {write_port}')
            writer = SerialWriter(port=write_port, baudrate=9600)
            for line in SAMPLE_DATA.split('\n'):
                writer.write(line)
                logging.info('wrote: %s', line)

        def _run_write_specialcase():
            writer = SerialWriter(port=write_port, quiet=True, eol="FOO\\n")
            writer.write(SPECIAL_STRING)
            logging.info('wrote: %s', SPECIAL_STRING)

        def _run_write_binary():
            writer = SerialWriter(port=write_port, encoding=None)
            for line in BINARY_DATA:
                writer.write(line)
                logging.info('wrote: %s', line)

        writer_thread = threading.Thread(target=_run_writer)
        writer_thread.start()
        logging.info('Started writer thread')
        self._run_reader(read_port)
        writer_thread.join()
        logging.info('Writer thread completed')

        writer_thread = threading.Thread(target=_run_write_specialcase)
        writer_thread.start()
        logging.info('Started special writer thread')
        self._run_read_specialcase(read_port)
        writer_thread.join()
        logging.info('Special writer thread completed')

        writer_thread = threading.Thread(target=_run_write_binary)
        writer_thread.start()
        logging.info('Started binary writer thread')
        self._run_read_binary(read_port)
        writer_thread.join()
        logging.info('Binary writer thread completed')


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
