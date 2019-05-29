#!/usr/bin/env python3

import json
import logging
import socket
import sys

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.formats import Text
from logger.utils.das_record import DASRecord
from logger.writers.writer import Writer

################################################################################
class NetworkWriter(Writer):
  """Write to network."""
  def __init__(self, network, num_retry=2):
    """
    Write text records to a network socket.

    NOTE: tcp is nominally implemented, but DOES NOT WORK!

    network      Network address to write, in host:port format (e.g.
                 'rvdas:6202'). If host is omitted (e.g. ':6202'),
                 broadcast via UDP on specified port.

    num_retry    Number of times to retry if write fails.
    """

    super().__init__(input_format=Text)

    if network.find(':') == -1:
      raise ValueError('NetworkWriter network argument must be in '
                       '\'host:port\' or \':port\' format. Found "%s"', network)
    self.network = network
    self.num_retry = num_retry

    (host, port) = network.split(':')
    port = int(port)

    # TCP if host is specified
    if host:
      self.socket = socket.socket(family=socket.AF_INET,
                                  type=socket.SOCK_STREAM,
                                  proto=socket.IPPROTO_TCP)
      # Should this be bind()?
      self.socket.connect((host, port))

    # UDP broadcast if no host specified. Note that there's some
    # dodginess I don't understand about networks: if '<broadcast>' is
    # specified, socket tries to send on *all* interfaces. if '' is
    # specified, it tries to send on *any* interface.
    else:
      host = '<broadcast>' # special code for broadcast
      self.socket = socket.socket(family=socket.AF_INET,
                                  type=socket.SOCK_DGRAM,
                                  proto=socket.IPPROTO_UDP)
      self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
      try: # Raspbian doesn't recognize SO_REUSEPORT
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
      except AttributeError:
        logging.warning('Unable to set socket REUSEPORT; system may not support it.')

      self.socket.connect((host, port))

  ############################
  def write(self, record):
    """Write the record to the network."""
    if not record:
      return

    # If record is not a string, try converting to JSON. If we don't know
    # how, throw a hail Mary and force it into str format
    if not type(record) is str:
      if type(record) in [int, float, bool, list, dict]:
        record = json.dumps(record)
      elif type(record) is DASRecord:
        record = record.as_json()
      else:
        record = str(record)

    num_tries = 0
    bytes_sent = 0
    rec_len = len(record)
    while num_tries < self.num_retry and bytes_sent < rec_len:
      bytes_sent = self.socket.send(record.encode('utf-8'))
      num_tries += 1

    logging.debug('NetworkWriter.write() wrote %d/%d bytes after %d tries',
                    bytes_sent, rec_len, num_tries)
