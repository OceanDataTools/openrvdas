#!/usr/bin/env python3
"""Read NMEA-formatted sensor data off the network as UDP packets,
parse and cache the values received and serve them to websocket
clients who have requested them.

A typical invocation aboard Sikuliaq might be:

    server/network_data_server.py \
      --read_network :53100,:53104,:53105,:53106,... \
      --parse_nmea_sensor_path test/sikuliaq/sensors.yaml \
      --parse_nmea_sensor_model_path test/sikuliaq/sensor_models.yaml \
      --websocket :8766

Note that aboard Sikuliaq, each instrument has its own UDP port, and
Sikuliaq-specific sensor definitions are in test/sikuliaq. Aboard the
NBP, where all instrument strings are broadcast on either 6221 or
6224, the invocation would be


    server/network_data_server.py \
      --read_network :6221,:6224 \
      --websocket :8766

Both of these invocations say to 

1. Listen on the UDP ports specified by --read_network for timestamped
   NMEA sentences

2. Parse those sentences using definitions in test/sikuliaq/....yaml
   (the default sensor and sensor_model definitions are in the
   local/sensor/ and local/sensor_model/ directories).

3. Store the resulting field-value-timestamps in an in-memory cache

4. Wait for clients to connect to the websocket at port 8766 and
   serve them the requested data.

The server listens for two types of requests:

1. If the request is the string "variables", return a list of the
   names of the variables the server has in cache and is able to
   serve. The server will continue listening for follow up messages,
   most likely this one:

2. If the request is a python dict, assume it is of the form:

    {field_1_name: {'seconds': num_secs},
     field_2_name: {'seconds': num_secs},
     ...}

   where seconds is a float representing the number of seconds of
   back data being requested.

   This field dict is passed to serve_fields(), which will to retrieve
   num_secs of back data for each of the specified fields and return it
   as a JSON-encoded dict of the form:

     {
       field_1_name: [(timestamp, value), (timestamp, value), ...],
       field_2_name: [(timestamp, value), (timestamp, value), ...],
       ...
     }

The server will then await a "ready" message from the client, and when
received, will loop and send a JSON-encoded dict of all the
(timestamp, value) tuples that have come in since the previous
request. It will continue this behavior indefinitely, waiting for a
"ready" request and sending updates.

At present, the code is configured to gather the data it serves via
UDP broadcasts.

"""
import asyncio
import json
import logging
import pprint
import sys
import threading
import time
import websockets

sys.path.append('.')

from logger.readers.composed_reader import ComposedReader
from logger.readers.network_reader import NetworkReader
from logger.transforms.parse_nmea_transform import ParseNMEATransform
from logger.utils import nmea_parser

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

################################################################################
# Global cache and lock which we'll share between network reader that
# fills it and websocket server that serves data from it.
cache = {}
cache_lock = threading.Lock()

################################################################################
class CachedDataServer:
  ############################
  def __init__(self, websocket, cache, cache_lock, interval=1):
    self.websocket = websocket

    self.cache = cache
    self.cache_lock = cache_lock
    self.interval = interval

    self.quit_flag = False

  ############################
  @asyncio.coroutine
  async def serve_data(self):
    """Start serving on websocket. Assumes we've got our own event loop."""

    while not self.quit_flag:
      client_request = await self.get_client_request()

      # If they've requested a list of the variables we've got, return
      # that and loop to wait for other requests.
      if client_request == 'variables':
        await self.serve_variables()

      # If they've handed us a dictionary, we assume keys are the
      # fields they want served.
      elif type(client_request) == dict:
        await self.serve_fields(client_request)

      else:
        logging.warning('Unrecognized client request: "%s"', client_request)

  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True

  ############################
  @asyncio.coroutine
  async def get_client_request(self):
    """Get the fields we're interested in having served.
    """
    message = await self.websocket.recv()
    logging.info('Received data request: "%s"', message)
    if not message:
      logging.info('Received empty data request, doing nothing.')
      return

    try:
      self.fields = json.loads(message)
      return self.fields
    except json.JSONDecodeError:
      logging.info('get_fields(): unparseable JSON request: "%s"', message)


  ############################
  @asyncio.coroutine
  async def serve_variables(self):
    """Send client a list of the variable names we're able to serve.
    """
    variables = self.cache.keys()
    send_message = json.dumps(variables)
    logging.info('Data server sending: %s', send_message)

    try:
      await self.websocket.send(send_message)
      logging.debug('Websocket sent data, awaiting ready...')
      ready_message = await self.websocket.recv()
      if not ready_message == 'ready':
        logging.error('DataServer non "ready" message: "%s"', ready_message)
      logging.debug('Websocket got ready...')
    except websockets.exceptions.ConnectionClosed:
      return

  ############################
  @asyncio.coroutine
  async def serve_fields(self, fields):
    """Serve data, if it exists, from cache. Format of JSON message is
        {
           field_name: [(timestamp, value), (timestamp, value),...],
           field_name: [(timestamp, value), (timestamp, value),...],
           field_name: [(timestamp, value), (timestamp, value),...],
        }
    """
    for field_name in fields:
      logging.info('Requesting field: %s, %g secs.', field_name,
                   fields[field_name].get('seconds', 0))

    # Keep track of the latest timestamp we've sent to a client, so we
    # only ever send new data.
    latest_timestamp_sent = {field_name: 0 for field_name in fields}

    while not self.quit_flag:
      now = time.time()
      results = {}
      for field_name, field_spec in fields.items():
        back_seconds = field_spec.get('seconds', 0)
        logging.info('Requesting field: %s, %g secs.', field_name, back_seconds)
        field_cache = self.cache.get(field_name, None)
        if field_cache is None:
          logging.info('No cached data for %s', field_name)
          continue

        # Do we have any results? Are they later than the ones we've
        # already sent?
        if not field_cache or not field_cache[-1]:
          continue
        if not field_cache[-1][0] > latest_timestamp_sent[field_name]:
          continue

        # If they don't want back data, just send the most recent result
        if not back_seconds:
          results[field_name] = [ field_cache[-1] ]

        # Otherwise, copy over records are in the now - back_seconds window.
        else:
          oldest_timestamp = now - back_seconds
          results[field_name] = [pair for pair in field_cache if
                                 pair[0] >= oldest_timestamp and
                                 pair[0] > latest_timestamp_sent[field_name]]

      # If we do have results, package them up and send them
      if results:
        # If we've not asked for back seconds on a field, then
        # assume(!) that user only wants most recent value at any
        # time. So if database has returned a bunch of values, still
        # only send user the most recent one for each field.
        for field_name in results:
          if len(results[field_name]) > 1:
            if not fields.get(field_name, {}).get('seconds', 0):
              results[field_name] = [results[field_name][-1]]

        send_message = json.dumps(results)
        logging.info('Data server sending %d bytes', len(send_message))
        try:
          await self.websocket.send(send_message)
          logging.debug('Websocket sent data, awaiting ready...')
          ready_message = await self.websocket.recv()
          if not ready_message == 'ready':
            logging.error('DataServer non "ready" message: "%s"', ready_message)
          logging.debug('Websocket got ready...')
        except websockets.exceptions.ConnectionClosed:
          return

        # Keep track of the latest timestamp we've sent for each
        # variable so that we don't repeat ourselves.  Each value
        # should be a list of (timestamp, value) pairs. Look at the
        # last timestamp in each value list.
        for field_name, field_results in results.items():
          if not field_results:
            continue
          latest_result = field_results[-1]
          if not latest_result:
            continue
          latest_result_timestamp = latest_result[0]
          if latest_result_timestamp > latest_timestamp_sent[field_name]:
            latest_timestamp_sent[field_name] = latest_result_timestamp

      # New results or not, take a nap before trying to fetch more results
      elapsed = time.time() - now
      time_to_sleep = max(0, self.interval - elapsed)
      logging.debug('Sleeping %g seconds', time_to_sleep)
      await asyncio.sleep(time_to_sleep)

############################
"""Top-level routine to read network data and put it in shared
cache. We'll run this in a separate thread."""
def read_data_from_network(cache, cache_lock, read_network,
                           back_seconds=30, cleanup_interval=10,
                           parse_nmea_message_path=None,
                           parse_nmea_sensor_path=None,
                           parse_nmea_sensor_model_path=None,
                           ):

  readers = [NetworkReader(network=network)
             for network in read_network.split(',')]
  transform = ParseNMEATransform(message_path=parse_nmea_message_path,
                                 sensor_path=parse_nmea_sensor_path,
                                 sensor_model_path=parse_nmea_sensor_model_path)
  reader = ComposedReader(readers=readers, transforms=[transform])

  # Every N seconds, we're going to detour to clean old data out of cache
  next_cleanup_time = time.time() + cleanup_interval

  while True:
    # Loop, getting records, until it's time for next cleanup
    while time.time() < next_cleanup_time:
      record = reader.read()

      logging.debug('Got record: %s', record)

      # If, for some reason, we get empty record try again
      if not record:
        continue

      # Add values from record to cache
      with cache_lock:
        for field, value in record.fields.items():
          if not field in cache:
            cache[field] = []
          cache[field].append((record.timestamp, value))

    #logging.warning('CACHE:\n%s', pprint.pformat(cache))

    # It's now cleanup time
    logging.info('Cleaning up cache')
    now = time.time()
    with cache_lock:
      for field in cache:
        value_list = cache[field]
        while value_list and value_list[0][0] < now - back_seconds:
          value_list.pop(0)
    next_cleanup_time = now + cleanup_interval

############################
"""Top-level coroutine for running DataServer."""
@asyncio.coroutine
async def serve_websocket_data(websocket, path):
  global cache, cache_lock

  logging.warning('New data websocket client attached: %s', path)
  data_server = CachedDataServer(websocket, cache, cache_lock)
  await data_server.serve_data()

################################################################################
################################################################################
if __name__ == '__main__':
  import argparse

  parser = argparse.ArgumentParser()

  # Optional address for websocket server from which we'll accept
  # connections from LoggerRunners willing to accept dispatched
  # configs.
  parser.add_argument('--websocket', dest='websocket',
                      default='8766', action='store',
                      help='Host:port on which to serve data')

  parser.add_argument('--read_network', dest='read_network', action='store',
                      help='Comma-separated list of network ports to listen '
                      'for data on, e.g. :6221,:6224')

  parser.add_argument('--parse_nmea_message_path',
                      dest='parse_nmea_message_path',
                      default=nmea_parser.DEFAULT_MESSAGE_PATH,
                      help='Comma-separated globs of NMEA message definition '
                      'file names, e.g. '
                      'local/message/*.yaml,test/skq/messages.yaml')
  parser.add_argument('--parse_nmea_sensor_path',
                      dest='parse_nmea_sensor_path',
                      default=nmea_parser.DEFAULT_SENSOR_PATH,
                      help='Comma-separated globs of NMEA sensor definition '
                      'file names, e.g. '
                      'local/sensor/*.yaml,test/skq/sensors.yaml')
  parser.add_argument('--parse_nmea_sensor_model_path',
                      dest='parse_nmea_sensor_model_path',
                      default=nmea_parser.DEFAULT_SENSOR_MODEL_PATH,
                      help='Comma-separated globs of NMEA sensor model '
                      'definition file names, e.g. '
                      'local/sensor_model/*.yaml,test/skq/sensor_models.yaml')

  parser.add_argument('--back_seconds', dest='back_seconds', action='store',
                      type=float, default=120,
                      help='Maximum number of seconds of old data to keep '
                      'for serving to new clients.')

  parser.add_argument('--cleanup_interval', dest='cleanup_interval',
                      action='store', type=float, default=60,
                      help='How often to clean old data out of the cache.')

  parser.add_argument('--interval', dest='interval', action='store',
                      type=float, default=1,
                      help='How many seconds to sleep between successive '
                      'sends of data to clients.')

  parser.add_argument('-v', '--verbosity', dest='verbosity', default=0,
                      action='count', help='Increase output verbosity')
  args = parser.parse_args()

  # Set logging verbosity
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  read_data_thread = threading.Thread(target=read_data_from_network,
                                      args=(cache, cache_lock,
                                            args.read_network,
                                            args.back_seconds,
                                            args.cleanup_interval,
                                            args.parse_nmea_message_path,
                                            args.parse_nmea_sensor_path,
                                            args.parse_nmea_sensor_model_path))
  read_data_thread.start()

  try:
    host, port = args.websocket.split(':')
    port = int(port)
  except ValueError:
    logging.error('--websocket argument must be host:port')
    sys.exit(1)

  try:
    event_loop = asyncio.get_event_loop()
    websocket_server = websockets.serve(serve_websocket_data, host, port)
    event_loop.run_until_complete(websocket_server)
    event_loop.run_forever()
  except OSError:
    logging.warning('Failed to open websocket %s:%s', host, port)
