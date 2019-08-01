#!/usr/bin/env python3

import asyncio
import json
import logging
import sys
import threading
import time
import websockets

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord
from logger.utils.cached_data_server import CachedDataServer
from logger.writers.writer import Writer

################################################################################
class CachedDataWriter(Writer):
  def __init__(self, data_server, start_server=False, back_seconds=480,
               cleanup_interval=6, update_interval=1):
    """Feed passed records to a CachedDataServer via a websocket. Expects
    records in DASRecord or dict formats. If the --start_server flag
    is True, try to start the server ourselves, using the rest of the provided
    parameters as defaults.

    data_server    [host:]port on which to look for data server

    back_seconds   Number of seconds of back data to hold in cache

    cleanup_interval   Remove old data every N seconds

    update_interval    Serve updates to websocket clients every N seconds

    start_server       If true, start the server ourselves
    """
    self.data_server = data_server
    self.websocket = None
    self.server = None
    self.back_seconds = back_seconds
    self.cleanup_interval = cleanup_interval

    # Event loop we'll use to asynchronously manage writes to websocket
    self.event_loop = asyncio.new_event_loop()
    self.send_queue = asyncio.Queue(loop=self.event_loop)

    if start_server:
      host_port = data_server.split(':')
      if len(host_port) > 1 and host_port[0] != 'localhost':
        raise ValueError('CachedDataWriter host specification for data server '
                         'must be either "localhost" or empty if starting '
                         'our own cached data server: "%s"' % host_port)
      self.port = int(host_port[-1])
      
      # Instantiate (and start) CachedDataServer
      self.server = CachedDataServer(port=port, interval=update_interval)

    # Start the thread that will asynchronously pull stuff from the
    # queue and send to the websocket. Also will, if we've got our oue
    # data server, run cleanup from time to time.
    self.cached_data_writer_thread = threading.Thread(
      name='cached_data_writer_thread',
      target=self._cached_data_writer_loop, daemon=True)
    self.cached_data_writer_thread.start()

  ############################
  def _cached_data_writer_loop(self):
    """Use an inner async function to pull stuff from the queue and send
    to the websocket. Also, if we've got our oue data server, run
    cleanup from time to time.
    """

    ############################
    async def _async_send_records_loop(self):
      """Inner async function that actually does websocket writes 
      and cleanups.
      """
      next_cleanup = 0
      while True:
        logging.info('CachedDataWriter trying to connect to '
                     + self.data_server)
        try:
          async with websockets.connect('ws://' + self.data_server) as ws:
            while True:
              try:
                record = self.send_queue.get_nowait()
                logging.debug('sending record: %s', record)
                record = {'type':'publish', 'data':record}
                await ws.send(json.dumps(record))
                response = await ws.recv()
                logging.debug('received response: %s', response)
              except asyncio.QueueEmpty:
                await asyncio.sleep(.2)

              # If we've started our own server, see if it's time to
              # clean up
              if self.server and time.time() > next_cleanup:
                now = time.time()
                self.server.cleanup(now - self.back_seconds)
                next_cleanup = now + self.cleanup_interval

        # If the websocket connection failed
        except OSError as e:
          logging.warning('CachedDataWriter websocket connection to %s '
                          'failed; sleeping before trying again: %s',
                          self.data_server, str(e))
          await asyncio.sleep(5)
          
    # Now call the async process in its own event loop
    self.event_loop.run_until_complete(_async_send_records_loop(self))
    self.event_loop.close()

  ############################
  def write(self, record):
    """Write out record. Expects passed records to be in one of two
    formats:

    1) DASRecord

    2) a dict encoding optionally a source data_id and timestamp and a
       mandatory 'fields' key of field_name: value pairs. This is the format
       emitted by default by ParseTransform:

       {
         'data_id': ...,
         'timestamp': ...,
         'fields': {
           field_name: value,    # use default timestamp of 'now'
           field_name: value,
           ...
         }
       }

    A twist on format (2) is that the values may either be a singleton
    (int, float, string, etc) or a list. If the value is a singleton,
    it is taken at face value. If it is a list, it is assumed to be a
    list of (value, timestamp) tuples, in which case the top-level
    timestamp, if any, is ignored.

       {
         'data_id': ...,
         'timestamp': ...,
         'fields': {
            field_name: [(timestamp, value), (timestamp, value),...],
            field_name: [(timestamp, value), (timestamp, value),...],
            ...
         }
       }

    """
    if not record:
      return

    # Convert to a dict - inefficient, I know...
    if type(record) is DASRecord:
      record = json.loads(record.as_json())
    if type(record) is dict:
      self.send_queue.put_nowait(record)
    else:
      logging.warning('CachedDataWriter got non-dict/DASRecord object of '
                      'type %s: %s', type(record), str(record))


