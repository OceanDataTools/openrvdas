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
from logger.writers.udp_writer import UDPWriter

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


class TestUDPWriter(unittest.TestCase):
    ############################
    def _handler(self, signum, frame):
        """If timeout fires, raise our custom exception"""
        logging.info('Read operation timed out')
        raise ReaderTimeout

    ############################
    # Actually run the UDPWriter in internal method
    def write(self, host, port, eol=None, data=None, interval=0, delay=0, encoding='utf-8', mc_interface=None, mc_ttl=3):
        writer = UDPWriter(destination=host, port=port, eol=eol, encoding=encoding, mc_interface=mc_interface, mc_ttl=mc_ttl)

        time.sleep(delay)
        for line in data:
            writer.write(line)
            time.sleep(interval)

    ############################
    #
    # NOTE: The only simple to really verify that it's broadcast, as apposed to
    #       unicast that we successfully read, is to do packet analysis in
    #       wireshark/tshark or similar.  But this test case will catch most
    #       breakage from other developemnt.
    #
    def test_broadcast(self):
        # Main method starts here
        host = "<broadcast>"
        port = 8001

        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
        sock.bind((host, port))

        # Start the writer
        threading.Thread(target=self.write,
                         args=(host, port),
                         kwargs={"data": SAMPLE_DATA, "interval": 0.1}).start()

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(3)
        try:
            # Check that we get the lines we expect from it
            for line in SAMPLE_DATA:
                record = sock.recv(mmap.PAGESIZE)
                logging.info('looking for "%s", got "%s"', line, record)
                if record:
                    record = record.decode('utf-8')
                self.assertEqual(line, record)
        except ReaderTimeout:
            self.assertTrue(False, 'UDPReader timed out in test - is port '
                            '%s open?' % addr)
        signal.alarm(0)

    ############################
    #
    # NOTE: We're really testing 2 things here: unicast output and handling odd
    #       `eol` parameter values (e.g., escaped oddness).
    #
    def test_unicast_with_eol(self):
        # Main method starts here
        host = ''
        port = 8002
        eol = '\\r\\n' # simulate escaped entry from config file

        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        sock.bind((host, port))

        # Start the writer
        threading.Thread(target=self.write,
                         args=(host, port),
                         kwargs={"data": SAMPLE_DATA, "interval": 0.1, "eol": eol}).start()

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(3)
        try:
            # Check that we get the lines we expect from it
            for line in SAMPLE_DATA:
                record = sock.recv(mmap.PAGESIZE)
                if record:
                    record = record.decode('utf-8')
                    line += eol.encode().decode('unicode_escape')
                    logging.info('looking for "%s", got "%s"', line, record)
                    self.assertEqual(line, record)
        except ReaderTimeout:
            self.assertTrue(False, 'UDPReader timed out in test - is port '
                            '%s open?' % addr)
        signal.alarm(0)

    ############################
    def test_binary(self):
        # Main method starts here
        host = ''
        port = 8003

        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        sock.bind((host, port))

        # Start the writer
        threading.Thread(target=self.write,
                         args=(host, port),
                         kwargs={"data": BINARY_DATA, "interval": 0.1, "encoding": None}).start()

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(3)
        try:
            # Check that we get the lines we expect from it
            for line in BINARY_DATA:
                record = sock.recv(mmap.PAGESIZE)
                logging.info('looking for "%s", got "%s"', line, record)
                self.assertEqual(line, record)
        except ReaderTimeout:
            self.assertTrue(False, 'UDPReader timed out in test - is port '
                            '%s open?' % addr)
        signal.alarm(0)

    ############################
    #
    # NOTE: This doesn't actually prove that your network can support multicast
    #       routing, which is complicated.  It's only verifying that we sent
    #       packets to a multicast address and received them, all locally.  So,
    #       it also doesn't really test the IGMP group membership stuff very
    #       well.  Again, packet analysis is really needed to prove it's
    #       working.
    #
    def test_multicast(self):
        # Main method starts here
        host = "239.192.0.100"
        port = 8004
        ttl = 3
        source_ip = socket.gethostbyname(socket.gethostname())

        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

        # join the multicast group
        logging.info("joing %s to multicast group %s", source_ip, host)
        # NOTE: Since these are both already encoded as binary by inet_aton(),
        #       we can just concatenate them.  Alternatively, could use
        #       struct.pack("4s4s", ...)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                        socket.inet_aton(host) + socket.inet_aton(source_ip))

        # bind to the mc host, port
        sock.bind((host, port))

        # Start the writer
        threading.Thread(target=self.write,
                         args=(host, port),
                         kwargs={"data": SAMPLE_DATA, "interval": 0.1, "mc_interface": source_ip, "mc_ttl": ttl}).start()

        # Set timeout we can catch if things are taking too long
        signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(3)
        try:
            # Check that we get the lines we expect from it
            for line in SAMPLE_DATA:
                record = sock.recv(mmap.PAGESIZE)
                logging.info('looking for "%s", got "%s"', line, record)
                if record:
                    record = record.decode('utf-8')
                self.assertEqual(line, record)
        except ReaderTimeout:
            self.assertTrue(False, 'UDPReader timed out in test - is port '
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
