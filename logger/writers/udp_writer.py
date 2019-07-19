#!/usr/bin/env python3

import json
import logging
import socket
import struct
import sys

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.formats import Text
from logger.utils.das_record import DASRecord
from logger.writers.network_writer import NetworkWriter

################################################################################
class UDPWriter(NetworkWriter):
  """Write UDP packets to network."""
  def __init__(self, port, destination='', interface='',
               ttl=3, num_retry=2, eol=''):
    """
    Write text records to a network socket.

    port         Port to which packets should be sent

    destination  If specified, either multicast group or unicast IP addr

    interface    If specified, the network interface to send from

    ttl          For multicast, how many network hops to allow

    num_retry    Number of times to retry if write fails.

    eol          If specified, an end of line string to append to record
                 before sending.
    """
    interface = interface or '0.0.0.0'  # 0.0.0.0 means use all/any interfaces
    self.num_retry = num_retry
    self.eol = eol

    self.socket = socket.socket(family=socket.AF_INET,
                                type=socket.SOCK_DGRAM,
                                proto=socket.IPPROTO_UDP)
    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    try: # Raspbian doesn't recognize SO_REUSEPORT
      self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
    except AttributeError:
      logging.warning('Unable to set socket REUSEPORT; may be unsupported')

    # Set the time-to-live for messages, in case of multicast
    self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL,
                           struct.pack('b', ttl))

    # Bind to interface, whether it is one passed in, or the 0.0.0.0
    # default that means send on all interfaces.
    self.socket.bind((interface, port))

    # If no destination, it's a broadcast; set flag allowing broadcast and
    # set dest to special string
    if not destination:
      self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
      destination = '<broadcast>'

    self.socket.connect((destination, port))

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

    logging.debug('UDPWriter.write() wrote %d/%d bytes after %d tries',
                    bytes_sent, rec_len, num_tries)
