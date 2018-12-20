#!/usr/bin/env python3

"""Async version of NetworkReader, designed to work, e.g. with
dataflow architecture in dataflow/ directory.
"""

import logging
import asyncio
import socket
import sys

sys.path.append('.')

from logger.readers.network_reader import NetworkReader

################################################################################
# Read to the specified file. If filename is empty, read to stdout.
class AsyncNetworkReader(NetworkReader):
  """
  Read text records from an async network socket.

  NOTE: tcp is nominally implemented, but DOES NOT WORK!
  """

  ############################  
  class ReadNetworkToQueueProtocol:
    def __init__(self, queue):
      logging.debug('AsyncNetworkReader initialized')
      self.queue = queue
      self.transport = None

    def connection_made(self, transport):
      logging.debug('AsyncNetworkReader connection made')
      self.transport = transport

    def datagram_received(self, data, addr):
      record = data.decode()
      logging.debug('AsyncNetworkReader enqueuing record: %s', record)
      self.queue.put_nowait(record)

  ############################
  def __init__(self, network):
    """
    network      Network address to read, in host:port format (e.g.
                 'rvdas:6202'). If host is omitted (e.g. ':6202'),
                 read via UDP on specified port.
    """

    # Our creator can check whether we've got an is_async attribute so
    # it knows whether to "await" our reads or simply call them.
    self.is_async = True

    if network.find(':') == -1:
      raise ValueError('NetworkReader network argument must be in '
                       '\'host:port\' or \':port\' format. Found "%s"', network)
    (host, port) = network.split(':')
    port = int(port)

    # Things that our protocol asynchronously reads off the network
    # will get thrown into this queue.
    self.in_queue = asyncio.Queue()

    # TCP if host is specified
    if host:
      net_socket = socket.socket(family=socket.AF_INET,
                                 type=socket.SOCK_STREAM,
                                 proto=socket.IPPROTO_TCP)
      # Should this be bind()?
      net_socket.connect((host, port))

    # UDP broadcast if no host specified. Note that there's some
    # dodginess I don't understand about networks: if '<broadcast>' is
    # specified, socket tries to send on *all* interfaces. if '' is
    # specified, it tries to send on *any* interface.
    else:
      net_socket = socket.socket(family=socket.AF_INET,
                                 type=socket.SOCK_DGRAM,
                                 proto=socket.IPPROTO_UDP)
      net_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
      try: # Raspbian doesn't recognize SO_REUSEPORT
        net_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
      except AttributeError:
        logging.warning('Unable to set socket REUSEPORT; may be unsupported.')
      net_socket.bind((host, port))

    # Create the connection using our pre-created socket and set it up
    # to run in whatever our current event loop is.
    loop = asyncio.get_event_loop()
    connection = loop.create_datagram_endpoint(
      lambda: self.ReadNetworkToQueueProtocol(self.in_queue),
      sock=net_socket)
    loop.run_until_complete(connection)
    
  ############################
  async def read(self):
    """
    Read the next network packet.
    """
    logging.debug('AsyncNetworkReader read() awaiting data')
    record = await self.in_queue.get()
    logging.info('AsyncNetworkReader returning record: %s', record)
    return record

