#!/usr/bin/env python3

import logging
import sys
import threading
import time

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.formats import Python_Record
from logger.utils.das_record import DASRecord
from logger.writers.writer import Writer

# Don't freak out if we can't find websockets - unless they actually
# try to instantiate a CachedDataWriter.
try:
  from logger.utils.cached_data_server import CachedDataServer
  CACHED_DATA_SERVER_OKAY = True
except ModuleNotFoundError:
  CACHED_DATA_SERVER_OKAY = False

################################################################################
class CachedDataWriter(Writer):
  def __init__(self, port, back_seconds=480, cleanup=60, interval=1):
    """A thin wrapper around CachedDataServer. Instantiate a
    CachedDataServer and feed the passed records into it. The
    CachedDataServer will start a websocket server on port 'port' and
    serve cached record data to clients who connect to it.

    port           port on which to serve websocket connections

    back_seconds   Number of seconds of back data to hold in cache

    cleanup        Remove old data every cleanup seconds

    interval       Serve updates to websocket clients every interval seconds
    """
    super().__init__(input_format=Python_Record)

    if not CACHED_DATA_SERVER_OKAY:
      raise RuntimeError('Unable to load logger/utils/cached_data_server.py. '
                         'Is websockets module properly installed?')
    self.port = port
    self.back_seconds = back_seconds
    self.cleanup = cleanup

    # Instantiate (and start) CachedDataServer
    self.server = CachedDataServer(port=port, interval=interval)

    # Start thread that will call server.cleanup() every 'cleanup' seconds
    threading.Thread(target=self.cleanup_loop, daemon=True).start()

  ############################
  def cleanup_loop(self):
    """Inner class to run in a thread, looping and cleaning up old records
    every 'cleanup' seconds.
    """
    while True:
      time.sleep(self.cleanup)
      now = time.time()
      self.server.cleanup(now - self.back_seconds)

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
    if record:
      self.server.cache_record(record)
