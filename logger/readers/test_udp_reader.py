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

SAMPLE_DATA = ['f1 line 1',
               'f1 line 2',
               'f1 line 3']

BINARY_DATA = [b'\xff\xa1',
               b'\xff\xa2',
               b'\xff\xa3']

# We're going to set MAXSIZE to 1K before writing this, and the fragmentation
# marker is 10 bytes long.  The first record here should fragment cleanly into
# all a's, all b's, and all c's, then get reassembled by the reader
# transparently.
BIG_DATA = ['a'*1014 + 'b'*1014 + 'c'*512,
            'all that is gold does not glitter',
            'not all who wsnder are lost',
            'the old that is strong does not wither',
            'deep roots are not reached by the frost',
            ]


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
    def write_udp(self, dest, port, data, mc_interface=None, encoding='utf-8', interval=0, delay=0):
        writer = UDPWriter(destination=dest, port=port, mc_interface=mc_interface, encoding=encoding)
        time.sleep(delay)
        for line in data:
            writer.write(line)
            time.sleep(interval)

    ############################
    def read_udp(self, interface, port, data, mc_group=None, encoding='utf-8', delay=0):
        time.sleep(delay)
        try:
            reader = UDPReader(interface=interface, port=port, mc_group=mc_group, encoding=encoding)
            for line in data:
                time.sleep(delay)
                logging.debug('UDPReader reading...')
                result = reader.read()
                # encode line and result, if needed, so we get nice consistent
                # b'whatever\n' output
                if encoding:
                    line_bytes = line.encode(encoding)
                    result_bytes = result.encode(encoding)
                else:
                    # want to break this one, and test exception handling?
                    # uncomment the next line.  i dare you.
                    #
                    #result += b'FOOO'
                    line_bytes = line
                    result_bytes = result
                logging.info('network wrote %s, read %s', line_bytes, result_bytes)
                self.assertEqual(line, result)
        except ReaderTimeout:
            self.assertTrue(False, 'UDPReader timed out in test - is port '
                            '%s:%s open?' % (interface, port))

    ############################
    # UNICAST
    def test_unicast(self):
        port = 8000
        dest = 'localhost'

        w_thread = threading.Thread(target=self.write_udp, name='write_thread',
                                    args=(dest, port, SAMPLE_DATA),
                                    kwargs={'interval': 0.1, 'delay': 0.2})

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(1)

        w_thread.start()
        self.read_udp(dest, port, SAMPLE_DATA)

        # Make sure everyone has terminated
        w_thread.join()

        # Silence the alarm
        signal.alarm(0)

    ############################
    # UNICAST raw/binary
    def test_unicast_binary(self):
        port = 8001
        dest = 'localhost'

        w_thread = threading.Thread(target=self.write_udp, name='write_thread',
                                    args=(dest, port, BINARY_DATA),
                                    kwargs={'encoding': None, 'interval': 0.1, 'delay': 0.2})

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(1)

        w_thread.start()
        self.read_udp(dest, port, BINARY_DATA, encoding=None)

        # Make sure everyone has terminated
        w_thread.join()

        # Silence the alarm
        signal.alarm(0)

    ############################
    # BROADCAST
    def test_broadcast(self):
        port = 8002
        dest = ''
        w_thread = threading.Thread(target=self.write_udp, name='write_thread',
                                    args=(dest, port, SAMPLE_DATA),
                                    kwargs={'interval': 0.1, 'delay': 0.2})

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(1)

        w_thread.start()
        self.read_udp(dest, port, SAMPLE_DATA)

        # Make sure everyone has terminated
        w_thread.join()

        # Silence the alarm
        signal.alarm(0)

    ############################
    # MULTICAST
    def test_multicast(self):
        port = 8003
        dest = '224.1.1.1'
        mc_interface = socket.gethostbyname(socket.gethostname())

        w_thread = threading.Thread(target=self.write_udp, name='multicast1',
                                    args=(dest, port, SAMPLE_DATA),
                                    kwargs={'mc_interface': mc_interface, 'interval': 0.1, 'delay': 0.2})

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(1)

        w_thread.start()
        self.read_udp(mc_interface, port, SAMPLE_DATA, dest)

        # Make sure everyone has terminated
        w_thread.join()

        # Silence the alarm
        signal.alarm(0)

    ############################
    # MULTICAST listening to the wrong group
    def test_multicast_wrong(self):
        port = 8004
        dest = '224.1.1.1'
        mc_interface = socket.gethostbyname(socket.gethostname())

        w_thread = threading.Thread(target=self.write_udp, name='multicast_wrong',
                                    args=(dest, port, SAMPLE_DATA, mc_interface))
        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(1)

        w_thread.start()

        # A thread listening to a different group should get nothing and
        # should therefore timeout.
        with self.assertRaises(AssertionError):
            self.read_udp(mc_interface, port, SAMPLE_DATA, '224.1.1.2')

        # Make sure everyone has terminated
        w_thread.join()

        # Silence the alarm
        signal.alarm(0)

    def test_fragmentation(self):
        port = 8005
        dest = 'localhost'

        w_thread = threading.Thread(target=self.write_udp, name='write_thread',
                                    args=(dest, port, BIG_DATA),
                                    kwargs={'interval': 0.1, 'delay': 0.2})

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(1)

        w_thread.start()
        self.read_udp(dest, port, BIG_DATA)

        # Make sure everyone has terminated
        w_thread.join()

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

    # import these down here so logger is already setup
    from logger.writers.udp_writer import UDPWriter
    from logger.readers.udp_reader import UDPReader

    # import the whole udp_reader module so we can override MAXSIZE
    import logger.writers.udp_writer as udp_writer
    udp_writer.MAXSIZE = 1024

    unittest.main(warnings='ignore')
