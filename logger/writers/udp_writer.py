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

############################
def check_is_ip_addr(ip_str):
  """Raise ValueError if the passed string is not a well-formed ip address."""
  tuples = ip_str.split('.')
  okay = len(tuples) == 4
  if okay:
    try:
      okay = False not in [int(t) < 256 for t in tuples]
    except ValueError:
      okay = False
  if not okay:
    raise ValueError('"%s" is not a valid IPv4 tuple' % ip_str)

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
    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)

    if interface and destination:
      check_is_ip_addr(interface)
      check_is_ip_addr(destination)
      # At the moment, we don't know how to do both interface and
      # multicast/unicast. If they've specified both, then complain
      # and ignore the interface part.
      logging.warning('UDPWriter doesn\'t yet support specifying both '
                      'interface and destination. Ignoring interface '
                      'specification.')

    # If they've specified the interface we're supposed to be sending
    # via, then we have to do a little legerdemain: we're going to
    # connect to the broadcast address of the specified interface as
    # our destination. The broadcast address is just the normal
    # address with the last tuple replaced by ".255".
    elif interface:
      check_is_ip_addr(interface)
      # Change interface's lowest tuple to 'broadcast' value (255)
      destination = interface[:interface.rfind('.')] + '.255'

    # If we've been given a destination, make sure it's a valid IP
    elif destination:
      check_is_ip_addr(destination)

    # If no destination, it's a broadcast; set flag allowing broadcast and
    # set dest to special string
    else:
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
