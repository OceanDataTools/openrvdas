#!/usr/bin/env python3

import logging
import signal
import socket
import sys
import threading
import time
import unittest
import warnings

sys.path.append('.')

from logger.writers.network_writer import NetworkWriter

SAMPLE_DATA = ['f1 line 1',
               'f1 line 2',
               'f1 line 3']

##############################
class ReaderTimeout(StopIteration):
  """A custom exception we can raise when we hit timeout."""
  pass

################################################################################
class TestNetworkWriter(unittest.TestCase):
  ############################
  def _handler(self, signum, frame):
    """If timeout fires, raise our custom exception"""
    logging.info('Read operation timed out')
    raise ReaderTimeout

  ############################
  # Actually run the NetworkWriter in internal method
  def write_network(self, addr, data, interval=0, delay=0):
    writer = NetworkWriter(addr)

    time.sleep(delay)
    for line in data:
      writer.write(line)
      time.sleep(interval)

  ############################
  def test_udp(self):
    # Main method starts here
    addr = ':8001'
    (host, port) = addr.split(':')
    port = int(port)
    sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
    sock.bind((host, port))

    # Start the writer
    threading.Thread(target=self.write_network,
                     args=(addr, SAMPLE_DATA, 0.1)).start()

    # Set timeout we can catch if things are taking too long
    signal.signal(signal.SIGALRM, self._handler)    
    signal.alarm(3)
    try:
      # Check that we get the lines we expect from it
      for line in SAMPLE_DATA:
        record = sock.recv(4096)
        if record:
          record = record.decode('utf-8')
        self.assertEqual(line, record)
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

  LOGGING_FORMAT = '%(asctime)-15s %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
  
  unittest.main(warnings='ignore')
