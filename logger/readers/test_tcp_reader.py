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

from logger.readers.tcp_reader import TCPReader
from logger.writers.tcp_writer import TCPWriter

SAMPLE_DATA = ['f1 line 1',
               'f1 line 2',
               'f1 line 3 is longer']

BINARY_DATA = [b'\xff\xa1',
               b'\xff\xa2\x42',
               b'\xff\xa3']


class ReaderTimeout(StopIteration):
    """A custom exception we can raise when we hit timeout."""
    pass

################################################################################
class TestTCPReader(unittest.TestCase):
    ############################
    def setUp(self):
        self.time_to_die = False

    ############################
    def tearDown(self):
        self.time_to_die = True

    ############################
    def _handler(self, signum, frame):
        """If timeout fires, raise our custom exception"""
        logging.info("Time's up")
        raise ReaderTimeout

    ############################
    def wonky_writer(self, dest, port, line, eol=None, encoding='utf-8', interval=0.2, delay=0):
        global time_to_die
        logging.debug('starting wonky writer')
        writer = TCPWriter(destination=dest, port=port, eol=eol, encoding=encoding)
        time.sleep(delay)
        while not self.time_to_die:
            writer.write(line)
            time.sleep(interval)

    def test_wonky_disconnect(self):
        dest_ip = '127.0.0.1'
        dest_port = 8010
        eol = '\n'
        line = 'hello there'
        encoding = 'utf-8'
        count=0

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(5)

        # do the whole thing in a try/catch looking for ReaderTimeout
        try:
            # create the reader
            reader = TCPReader(str(socket.INADDR_ANY), dest_port, eol=eol, encoding=encoding)

            # start the wonky_writer thread
            w_thread = threading.Thread(target=self.wonky_writer, name='wonky_writer',
                                        args=(dest_ip, dest_port, line, eol))
            w_thread.start()

            # read a line (a few lines, actually), teardown, start another
            # reader, read a few lines
            time.sleep(1)
            record = reader.read()
            record_bytes = record.encode(encoding)
            line_bytes = line.encode(encoding)
            logging.info('first reader looking for %s, got %s', line_bytes, record_bytes)
            self.assertEqual(line, record)
            count += 1

            logging.info("deleting initial reader")
            del reader
            time.sleep(2)

            logging.info("creating 2nd reader")
            reader = TCPReader(str(socket.INADDR_ANY), dest_port, eol=eol, encoding=encoding)
            
            while True:
                record = reader.read()
                line_bytes = line.encode(encoding)
                record_bytes = record.encode(encoding)
                logging.info('2nd reader looking for %s, got %s', line_bytes, record_bytes)
                self.assertEqual(line, record)
                count += 1

        except ReaderTimeout:
            passing = 6
            self.assertTrue(count >= passing , 'Failed to receive at least %d records (received %d)' % (passing, count))
        signal.alarm(0)

        logging.info('received %d records', count)
        self.time_to_die = True
        w_thread.join()
        
    ############################
    def do_the_test(self, dest_ip=None, dest_port=None, eol=None, encoding='utf-8', sample_data=SAMPLE_DATA, alarm_timeout=3):
        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(alarm_timeout)

        # do the whole thing in a try/catch looking for ReaderTimeout
        try:
            # create the reader
            reader = TCPReader(str(socket.INADDR_ANY), dest_port, eol=eol, encoding=encoding)
            
            # create the writer and pump all our data into the socket in one big blob
            writer = TCPWriter(dest_ip, dest_port, eol=eol, encoding=encoding)
            for line in sample_data:
                writer.write(line)

            # now make sure our reader can pluck the individual records out of the stream
            for line in sample_data:
                if eol:
                    # if `eol`, the reader can detect individual messages for us
                    record = reader.read()
                else:
                    # otherwise it's up to us to know how much to read out of
                    # the stream
                    record = reader.read(len(line))
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
    def test_text_by_size(self):
        kwargs = { 'dest_ip': '127.0.0.1',
                   'dest_port': 8001,
                   'eol': None,
        }
        self.do_the_test(**kwargs)


    ############################
    def test_text_by_eol(self):
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
                   'eol': b'\xffFOO\xff',
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
