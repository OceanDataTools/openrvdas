#!/usr/bin/env python3

import logging
import socket
import sys

sys.path.append('.')

from logger.utils.formats import Text
from logger.readers.reader import Reader

BUFFER_SIZE = 4096

################################################################################
# Read to the specified file. If filename is empty, read to stdout.
class NetworkReader(Reader):
  """
  Read text records from a network socket.

  NOTE: tcp is nominally implemented, but DOES NOT WORK!

  TODO: code won't handle records that are larger than 4K right now,
  which, if we start getting into Toby Martin's Total Metadata Ingestion
  (TMI), may not be enough. We'll need to implement something that will
  aggregate recv()'s and know when it's got an entire record?
  """
  ############################
  def __init__(self, network, buffer_size=BUFFER_SIZE):
    """

    network      Network address to read, in host:port format (e.g.
                 'rvdas:6202'). If host is omitted (e.g. ':6202'),
                 read via UDP on specified port.
    """
    super().__init__(output_format=Text)

    self.network = network
    self.buffer_size = buffer_size
    if network.find(':') == -1:
      raise ValueError('NetworkReader network argument must be in '
                       '\'host:port\' or \':port\' format. Found "%s"', network)
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
      host = '' # special code for broadcast
      self.socket = socket.socket(family=socket.AF_INET,
                                  type=socket.SOCK_DGRAM,
                                  proto=socket.IPPROTO_UDP)
      self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
      try: # Raspbian doesn't recognize SO_REUSEPORT
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
      except AttributeError:
        logging.warning('Unable to set socket REUSEPORT; system may not support it.')
      self.socket.bind((host, port))

  ############################
  def read(self):
    """
    Read the next network packet.
    """
    record = self.socket.recv(self.buffer_size)
    logging.debug('NetworkReader.read() received %d bytes', len(record))
    if record:
      record = record.decode('utf-8')
    return record
