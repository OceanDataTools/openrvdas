#!/usr/bin/env python3

import logging
import os
import select
import sys
import tty
import tempfile
import time
import threading
import unittest
import warnings

sys.path.append('.')
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
    """Create a pair of virtual serial ports using os.openpty() and bridge them.

    Two pty pairs are created. The slave ends are symlinked to the requested
    port names so that pyserial can open them by path. A bridge thread copies
    data between the two master ends, emulating the loopback that socat would
    normally provide.
    """
    ############################
    def __init__(self, port,
                 baudrate=9600, bytesize=8, parity='N', stopbits=1,
                 timeout=None, xonxoff=False, rtscts=False, write_timeout=None,
                 dsrdtr=False, inter_byte_timeout=None, exclusive=None):
        """We'll create two virtual ports: 'port' and 'port_in'; we will write
        to port_in and read the values back out from port."""
        self.read_port = port
        self.write_port = port + '_in'
        self.quit_flag = False
        self._fds = []  # all open fds, closed on quit

        try:
            master1, slave1 = os.openpty()
            master2, slave2 = os.openpty()
            self._fds = [master1, slave1, master2, slave2]
            self._master1 = master1
            self._master2 = master2

            # Put ptys in raw mode immediately so the line discipline does not
            # strip high bits or apply any cooked-mode transformations before
            # pyserial configures the slaves.
            tty.setraw(master1)
            tty.setraw(master2)

            # Expose slave ends at the paths pyserial will open
            for path, slave_fd in [(self.read_port, slave1),
                                   (self.write_port, slave2)]:
                if os.path.lexists(path):
                    os.unlink(path)
                os.symlink(os.ttyname(slave_fd), path)
        except OSError as e:
            logging.error('Failed to create virtual serial ports: %s', e)
            self.quit_flag = True

    ############################
    def _run_bridge(self):
        """Forward bytes between the two pty master ends until quit_flag is set."""
        try:
            while not self.quit_flag:
                r, _, _ = select.select([self._master1, self._master2], [], [], 0.1)
                for fd in r:
                    data = os.read(fd, 4096)
                    if data:
                        other = self._master2 if fd == self._master1 else self._master1
                        os.write(other, data)
        except OSError:
            pass
        finally:
            for path in [self.read_port, self.write_port]:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            for fd in self._fds:
                try:
                    os.close(fd)
                except OSError:
                    pass

    ############################
    def run(self):
        """Start the bridge thread."""
        self._bridge_thread = threading.Thread(target=self._run_bridge, daemon=True)
        self._bridge_thread.start()

    ############################
    def quit(self):
        self.quit_flag = True


################################################################################
class TestSerialWriter(unittest.TestCase):
    ############################
    # Set up simulated serial in/out ports
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
            self.skipTest('Could not create virtual serial ports')
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
