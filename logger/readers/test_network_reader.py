#!/usr/bin/env python3

import logging
import socket
import sys
import threading
import time
import unittest
import warnings

sys.path.append('.')

from logger.readers.network_reader import NetworkReader

SAMPLE_DATA = ['f1 line 1',
               'f1 line 2',
               'f1 line 3']

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
    host = '<broadcast>' # special code for broadcast
    sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
    sock.connect((host, port))

  time.sleep(delay)
  for line in data:
    #logging.debug('Writing line "%s"', line)
    sock.send(line.encode('utf-8'))
    time.sleep(interval)

    
################################################################################
class TestNetworkReader(unittest.TestCase):

  ############################
  def test_udp(self):
    addr = ':8000'
    reader = NetworkReader(addr)
    
    threading.Thread(target=write_network(addr, SAMPLE_DATA, 0.1)).start()
  
    for line in SAMPLE_DATA:
      logging.debug('NetworkReader reading...')
      self.assertEqual(line, reader.read())

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
