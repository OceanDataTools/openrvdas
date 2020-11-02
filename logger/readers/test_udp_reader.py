#!/usr/bin/env python3

import logging
import signal
import sys
import threading
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.udp_writer import UDPWriter  # noqa: E402
from logger.readers.udp_reader import UDPReader  # noqa: E402

SAMPLE_DATA = ['f1 line 1',
               'f1 line 2',
               'f1 line 3']
EOL_SAMPLE_DATA = ['f1 line 1\nf1 line 1a\nf1 line 1b\n',
                   'f1 line 2',
                   '\nf1 line 3',
                   '\n']


##############################
class ReaderTimeout(StopIteration):
    """A custom exception we can raise when we hit timeout."""
    pass


################################################################################
class TestUDPReader(unittest.TestCase):
    ############################
    def _handler(self, signum, frame):
        """If timeout fires, raise our custom exception"""
        logging.info('Read operation timed out')
        raise ReaderTimeout

    ############################
    def write_udp(self, port, dest, data, eol=None, interval=0, delay=0):
        writer = UDPWriter(port=port, destination=dest, eol=eol)
        time.sleep(delay)
        for line in data:
            writer.write(line)
            time.sleep(interval)

    ############################
    def read_udp(self, port, source, data, eol=None, interval=0, delay=0):
        time.sleep(delay)
        try:
            reader = UDPReader(port=port, source=source, eol=eol)
            for line in data:
                time.sleep(0.1)
                logging.debug('UDPReader reading...')
                result = reader.read()
                logging.info('network wrote "%s", read "%s"', line, result)
                self.assertEqual(line, result)
        except ReaderTimeout:
            self.assertTrue(False, 'UDPReader timed out in test - is port '
                            '%s:%s open?' % (source, port))

    ############################
    def test_udp(self):
        port = 8000

        #########
        # BROADCAST
        dest = ''
        w_thread = threading.Thread(target=self.write_udp, name='write_thread',
                                    args=(port, dest, SAMPLE_DATA, None, 0.1, 0.2))
        r1_thread = threading.Thread(target=self.read_udp, name='read_thread_1',
                                     args=(port, dest, SAMPLE_DATA, None, 0.1))
        r2_thread = threading.Thread(target=self.read_udp, name='read_thread_2',
                                     args=(port, dest, SAMPLE_DATA, None, 0.1))

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(1)

        w_thread.start()
        r1_thread.start()
        r2_thread.start()

        # Make sure everyone has terminated
        w_thread.join()
        r1_thread.join()
        r2_thread.join()

        # Silence the alarm
        signal.alarm(0)

        #########
        # MULTICAST
        dest = '224.1.1.1'
        w_thread = threading.Thread(
            target=self.write_udp, name='multicast1',
            args=(port, dest, SAMPLE_DATA, None, 0.1, 0.2))
        r1_thread = threading.Thread(
            target=self.read_udp, name='multicast2',
            args=(port, dest, SAMPLE_DATA, None, 0.1))
        r2_thread = threading.Thread(
            target=self.read_udp, name='multicast3',
            args=(port, dest, SAMPLE_DATA, None, 0.1))

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(1)

        w_thread.start()
        r1_thread.start()
        r2_thread.start()

        # Make sure everyone has terminated
        w_thread.join()
        r1_thread.join()
        r2_thread.join()

        # Silence the alarm
        signal.alarm(0)

        #########
        # MULTICAST listening to the wrong group
        dest = '224.1.1.1'
        w_thread = threading.Thread(
            target=self.write_udp, name='multicast_wrong',
            args=(port, dest, SAMPLE_DATA, None, 0.1, 0.2))
        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(1)

        w_thread.start()

        # A thread listening to a different group should get nothing and
        # should therefore timeout.
        with self.assertRaises(AssertionError):
            self.read_udp(port, '224.1.1.2', SAMPLE_DATA, None, 0.1)

        # Make sure everyone has terminated
        w_thread.join()

        # Silence the alarm
        signal.alarm(0)

    ############################
    def test_udp_eol(self):
        port = 8001
        dest = ''

        w_thread = threading.Thread(
            target=self.write_udp, name='eol_write_thread',
            args=(port, dest, EOL_SAMPLE_DATA, None, 0.1, 0.2))
        r1_thread = threading.Thread(
            target=self.read_udp, name='eol_read_thread_1',
            args=(port, dest, EOL_SAMPLE_DATA, None, 0.1))
        r2_thread = threading.Thread(
            target=self.read_udp, name='eol_read_thread_2',
            args=(port, dest, EOL_SAMPLE_DATA, None, 0.1))

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(1)

        w_thread.start()
        r1_thread.start()
        r2_thread.start()

        # Make sure everyone has terminated
        w_thread.join()
        r1_thread.join()
        r2_thread.join()

        # Silence the alarm
        signal.alarm(0)


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
