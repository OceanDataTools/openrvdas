#!/usr/bin/env python3

import logging
import mmap
import signal
import socket
import sys
import threading
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.tcp_writer import TCPWriter  # noqa: E402

SAMPLE_DATA = ['f1 line 1',
               'f1 line 2',
               'f1 line 3']

BINARY_DATA = [b'\xff\xa1',
               b'\xff\xa2',
               b'\xff\xa3']


class ReaderTimeout(StopIteration):
    """A custom exception we can raise when we hit timeout."""
    pass

################################################################################


class TestTCPWriter(unittest.TestCase):
    ############################
    def _handler(self, signum, frame):
        """If timeout fires, raise our custom exception"""
        logging.info('Read operation timed out')
        raise ReaderTimeout

    ############################
    # Actually run the TCPWriter in internal method
    def write_tcp(self, dest_ip, dest_port, eol, encoding, sample_data, interval, delay):
        writer = TCPWriter(dest_ip, dest_port, eol=eol, encoding=encoding)

        time.sleep(delay)
        for line in sample_data:
            writer.write(line)
            time.sleep(interval)

    ############################
    def do_the_test(self, dest_ip=None, dest_port=None, eol=None, encoding='utf-8', sample_data=SAMPLE_DATA, interval=0.1, delay=0, alarm_timeout=3):
        s = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)

        # use INADDR_ANY, but python bind() takes a string
        s.bind((str(socket.INADDR_ANY), dest_port))
        s.listen()

        # Start the writer
        threading.Thread(target=self.write_tcp,
                         args=(dest_ip, dest_port, eol, encoding, sample_data, interval, delay)).start()

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(alarm_timeout)
        try:
            # accept connections
            s_connected, client_addr = s.accept()
            logging.info('got connection from %s', client_addr)

            # Check that we get the lines we expect from it
            for line in sample_data:
                record = s_connected.recv(mmap.PAGESIZE)
                if encoding:
                    record = record.decode(encoding=encoding)
                # add eol to expected line before comparison
                if eol:
                    if encoding:
                        eol = eol.encode(encoding).decode('unicode_escape')
                    line += eol
                # encode line and record, if needed, so we get nice consistent
                # b'whatever\n' output
                if encoding:
                    line_bytes = line.encode(encoding)
                    record_bytes = record.encode(encoding)
                else:
                    line_bytes = line
                    record_bytes = record
                logging.info('looking for %s, got %s', line_bytes, record_bytes)
                self.assertEqual(line, record)
        except ReaderTimeout:
            self.assertTrue(False, 'NetworkReader timed out in test - is port '
                            '%s open?' % addr)
        signal.alarm(0)


    ############################
    def test_text(self):
        kwargs = { 'dest_ip': '127.0.0.1',
                   'dest_port': 8001,
                   'eol': None,
        }
        self.do_the_test(**kwargs)


    ############################
    def test_text_with_eol(self):
        kwargs = { 'dest_ip': '127.0.0.1',
                   'dest_port': 8002,
                   'eol': '\r\n',
        }
        self.do_the_test(**kwargs)


    ############################
    def test_text_with_crazy_eol(self):
        kwargs = { 'dest_ip': '127.0.0.1',
                   'dest_port': 8003,
                   'eol': 'FOO\\r\\n',
        }
        self.do_the_test(**kwargs)


    ############################
    def test_binary(self):
        kwargs = { 'dest_ip': '127.0.0.1',
                   'dest_port': 8004,
                   'eol': None,
                   'encoding': '',
                   'sample_data': BINARY_DATA,
        }
        self.do_the_test(**kwargs)


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
