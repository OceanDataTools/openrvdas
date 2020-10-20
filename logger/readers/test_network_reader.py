#!/usr/bin/env python3

import logging
import signal
import socket
import sys
import threading
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.network_reader import NetworkReader  # noqa: E402

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


############################
def write_network(addr, data, interval=0, delay=0):
    (host, port) = addr.split(':')
    port = int(port)

    # TCP if host is specified
    if host:
        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
        # Should this be bind()?
        sock.connect((host, port))
    else:
        host = '<broadcast>'  # special code for broadcast
        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
        try:  # Raspbian doesn't recognize SO_REUSEPORT
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
        except AttributeError:
            logging.warning('Unable to set socket REUSEPORT; system may not support it.')

        sock.connect((host, port))

    time.sleep(delay)
    for line in data:
        # logging.debug('Writing line "%s"', line)
        sock.send(line.encode('utf-8'))
        time.sleep(interval)


################################################################################
class TestNetworkReader(unittest.TestCase):
    ############################
    def _handler(self, signum, frame):
        """If timeout fires, raise our custom exception"""
        logging.info('Read operation timed out')
        raise ReaderTimeout

    ############################
    def test_udp(self):
        addr = ':8000'

        threading.Thread(target=write_network,
                         args=(addr, SAMPLE_DATA, 0.1, 0.2)).start()

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(5)
        try:
            reader = NetworkReader(addr)
            for line in SAMPLE_DATA:
                time.sleep(0.1)
                logging.debug('NetworkReader reading...')
                result = reader.read()
                logging.info('network wrote "%s", read "%s"', line, result)
                self.assertEqual(line, result)
        except ReaderTimeout:
            self.assertTrue(False, 'NetworkReader timed out in test - is port '
                            '%s open?' % addr)
        signal.alarm(0)

    ############################
    def test_udp_eol(self):
        addr = ':8001'

        threading.Thread(target=write_network,
                         args=(addr, EOL_SAMPLE_DATA, 0.1, 0.2)).start()

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(5)
        try:
            reader = NetworkReader(addr, eol='\n')
            result = reader.read()
            self.assertEqual(['f1 line 1', 'f1 line 1a', 'f1 line 1b'], result)
            result = reader.read()
            self.assertEqual('f1 line 2', result)
            result = reader.read()
            self.assertEqual('f1 line 3', result)
        except ReaderTimeout:
            self.assertTrue(False, 'NetworkReader timed out in test - is port '
                            '%s open?' % addr)
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
