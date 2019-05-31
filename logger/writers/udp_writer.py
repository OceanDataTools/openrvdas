#!/usr/bin/env python3

import json
import logging
import socket
import sys

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.formats import Text
from logger.utils.das_record import DASRecord
from logger.writers.network_writer import NetworkWriter

################################################################################
class UDPWriter(NetworkWriter):
  """Write UDP packets to network."""
  def __init__(self, network, num_retry=2, eol=''):
    """
    Write text records to a network socket.

    network      Network address to write, in interface:port format (e.g.
                 '192.168.52.1:6202'). If interface is omitted (e.g. ':6202'),
                 broadcast on all network interfaces.

    num_retry    Number of times to retry if write fails.

    eol          If specified, an end of line string to append to record
                 before sending.
    """
    if network.find(':') == -1:
      raise ValueError('UDPWriter network argument must be in \'host:port\' '
                       'or \':port\' format. Found "%s"' % network)
    self.network = network
    self.num_retry = num_retry
    self.eol = eol
    (interface, port) = network.split(':')
    port = int(port)

    self.socket = socket.socket(family=socket.AF_INET,
                                type=socket.SOCK_DGRAM,
                                proto=socket.IPPROTO_UDP)
    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    try: # Raspbian doesn't recognize SO_REUSEPORT
      self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
    except AttributeError:
      logging.warning('Unable to set socket REUSEPORT; system may not '
                      'support it.')
    # If interface is defined, bind to it; otherwise broadcast on all
    # network interfaces.
    if interface:
      self.socket.bind((interface, port))
    self.socket.connect(('<broadcast>', port))

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
    if self.eol:
      record += self.eol

    num_tries = 0
    bytes_sent = 0
    rec_len = len(record)
    while num_tries < self.num_retry and bytes_sent < rec_len:
      bytes_sent = self.socket.send(record.encode('utf-8'))
      num_tries += 1

    logging.debug('NetworkWriter.write() wrote %d/%d bytes after %d tries',
                    bytes_sent, rec_len, num_tries)
