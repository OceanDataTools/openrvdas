#!/usr/bin/env python3

import logging
import os
import subprocess
import sys
import tempfile
import time
import threading
import unittest
import warnings

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.serial_reader import SerialReader  # noqa: E402
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


class SimSerialPort:
    """Create a virtual serial port and feed stored logfile data to it."""
    ############################

    def __init__(self, port,
                 baudrate=9600, bytesize=8, parity='N', stopbits=1,
                 timeout=None, xonxoff=False, rtscts=False, write_timeout=None,
                 dsrdtr=False, inter_byte_timeout=None, exclusive=None):
        """We'll create two virtual ports: 'port' and 'port_in'; we will write
        to port_in and read the values back out from port."""
        self.read_port = port
        self.write_port = port + '_in'

        self.serial_params = {'baudrate': baudrate,
                              'byteside': bytesize,
                              'parity': parity,
                              'stopbits': stopbits,
                              'timeout': timeout,
                              'xonxoff': xonxoff,
                              'rtscts': rtscts,
                              'write_timeout': write_timeout,
                              'dsrdtr': dsrdtr,
                              'inter_byte_timeout': inter_byte_timeout,
                              'exclusive': exclusive}
        self.quit_flag = False

        # Finally, find path to socat executable
        self.socat_path = None
        for socat_path in ['/usr/bin/socat', '/usr/local/bin/socat']:
            if os.path.exists(socat_path) and os.path.isfile(socat_path):
                self.socat_path = socat_path
        if not self.socat_path:
            logging.error('Executable "socat" not found on path. Please refer '
                          'to installation guide to install socat.')
            self.quit_flag = True

    ############################
    def _run_socat(self):
        """Internal: run the actual command."""
        verbose = '-d'
        write_port_params = 'pty,link=%s,raw,echo=0' % self.write_port
        read_port_params = 'pty,link=%s,raw,echo=0' % self.read_port

        cmd = [self.socat_path,
               verbose,
               # verbose,   # repeating makes it more verbose
               read_port_params,
               write_port_params,
               ]
        try:
            # Run socat process using Popen, checking every second or so whether
            # it's died (poll() != None) or we've gotten a quit signal.
            logging.info('Calling: %s', ' '.join(cmd))
            socat_process = subprocess.Popen(cmd)
            while not self.quit_flag and not socat_process.poll():
                try:
                    socat_process.wait(1)
                except subprocess.TimeoutExpired:
                    pass

        except Exception as e:
            logging.error('ERROR: socat command: %s', e)

        # If here, process has terminated, or we've seen self.quit_flag. We
        # want both to be true: if we've terminated, set self.quit so that
        # 'run' loop can exit. If self.quit_flag, terminate process.
        if self.quit_flag:
            socat_process.kill()

            # TODO: Need to delete simulated ports!
        else:
            self.quit_flag = True
        logging.info('Finished: %s', ' '.join(cmd))

    ############################
    def run(self):
        """Create the virtual port with socat and start feeding it records from
        the designated logfile. If loop==True, loop when reaching end of input."""
        self.socat_thread = threading.Thread(target=self._run_socat, daemon=True)
        self.socat_thread.start()

    ############################
    def quit(self):
        self.quit_flag = True


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

    def _run_reader(self, port):
        reader = SerialReader(port)
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
        temp_port = self.tmpdirname + '/readline'
        temp_port_in = temp_port + '_in'

        sim_serial = SimSerialPort(temp_port)
        if sim_serial.quit_flag:
            return
        sim_serial.run()

        # Give it a moment to get started
        time.sleep(0.1)

        def _run_writer(in_port):
            writer = SerialWriter(port=in_port)
            for line in SAMPLE_DATA.split('\n'):
                writer.write(line)
                logging.info('wrote: %s', line)

        def _run_write_specialcase(in_port):
            writer = SerialWriter(in_port, quiet=True, eol="FOO\\n")
            writer.write(SPECIAL_STRING)
            logging.info('wrote: %s', SPECIAL_STRING)

        def _run_write_binary(in_port):
            writer = SerialWriter(in_port, encoding=None)
            for line in BINARY_DATA:
                writer.write(line)
                logging.info('wrote: %s', line)

        writer_thread = threading.Thread(target=_run_writer,
                                         kwargs={'in_port': temp_port_in})
        writer_thread.start()
        logging.info('Started writer thread')
        self._run_reader(temp_port)
        writer_thread.join()
        logging.info('Writer thread completed')

        writer_thread = threading.Thread(target=_run_write_specialcase,
                                         kwargs={'in_port': temp_port_in})
        writer_thread.start()
        logging.info('Started special writer thread')
        self._run_read_specialcase(temp_port)
        writer_thread.join()
        logging.info('Special writer thread completed')

        writer_thread = threading.Thread(target=_run_write_binary,
                                         kwargs={'in_port': temp_port_in})
        writer_thread.start()
        logging.info('Started binary writer thread')
        self._run_read_binary(temp_port)
        writer_thread.join()
        logging.info('Binary writer thread completed')

        # Tell simulated serial port to shut down
        sim_serial.quit()


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
