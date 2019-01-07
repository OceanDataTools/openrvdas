#!/usr/bin/env python3
"""NOTE: See below for mysterious cache behavior when invoked via
logger_manager.py

Accept data in DASRecord or dict format via the cache_record()
method, then serve it to anyone who connects via a websocket. A
CachedDataServer can be instantiated by running this script from the
command line and providing one or more UDP ports on which to listen
for NMEA-formatted data. It may also be instantiated as part of a
CachedDataWriter that can be invoked on the command line via the
listen.py script of via a configuration file.

The following direct invocation of this script

    logger/utils/cached_data_server.py \
      --network :6221,:6224 \
      --websocket :8766 \
      --back_seconds 480 \
      --v

says to

1. Listen on the UDP ports specified by --network for timestamped
   NMEA sentences

2. Parse those sentences into DASRecords

3. Store the resulting field-value-timestamps in an in-memory cache

4. Wait for clients to connect to the websocket at port 8766 and
   serve them the requested data.

If your data contain NMEA records that are not defined in local/, you
can modify the default sensor, sensor_model and message definition
paths with the --parse_nmea_[sensor,sensor_model,message]_path
arguments, such as

    logger/utils/cached_data_server.py \
      --network :6221,:6224 \
      --websocket :8766 \
      --back_seconds 480 \
      --parse_nmea_sensor_path local/sensor/*.yaml,test/sikuliaq/sensors.yaml \
      --parse_nmea_sensor_model_path local/sensor_model/*.yaml,test/sikuliaq/sensor_models.yaml \
      --v

When invoked via the listen.py script, fewer options are currently
available:

    logger/listener/listen.py \
      --network :6221,:6224 \
      --transform_parse_nmea \
      --write_cached_data_server :8766

This command line creates a CachedDataWriter that performs the same
function as the cached_data_server.py invocation above.

Note that the listen.py script currently provides no way to override
the default values for back_seconds (480) and cleanup (60). But a
contributor who wished could easily add the appropriate flags to the
listen.py script.

Finally, it may be incorporated (again, within its CachedDataWriter
wrapper) into a logger via a configuration file:

    logger/listener/listen.py --config_file data_server_config.yaml

where data_server_config.yaml contains:

    {
        "readers": [
            { "class": "NetworkReader",
              "kwargs": { "network": ":6221" }
            },
            { "class": "NetworkReader",
              "kwargs": { "network": ":6224" }
            }
        ],
        "transforms": [
            { "class": "ParseNMEATransform" }
        ],
        "writers": [
            { "class": "CachedDataWriter",
              "kwargs": { "websocket": ":8766",
                          "back_seconds": 480,
                          "cleanup": 60"
                        }
            }
        ]
    }

*****************
NOTE: We get have some inexplicable behavior here. When called
directly using the __main__ below or via a config with listen.py,
everything works just fine.

But for reasons I can't fathom, when launched from logger_runner.py or
logger_manager.py, it fails mysteriously. Specifically: the Connection
objects spawned by the asyncio websocket server only ever get the
initial copy of the (empty) cache, regardless of what's in the shared
cache.

See note in _serve_websocket_data() for site of behavior.
*****************

"""
import asyncio
import json
import logging
import sys
import threading
import time
import websockets

sys.path.append('.')

from logger.utils.das_record import DASRecord

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

############################
class WebSocketConnection:
  """Handle the websocket connection, serving data as requested."""
  ############################
  def __init__(self, websocket, cache, cache_lock, interval):
    self.websocket = websocket
    self.cache = cache
    self.cache_lock = cache_lock
    self.interval = interval
    self.quit_flag = False

  ############################
  def closed(self):
    """Has our client closed the connection?"""
    return self.quit_flag

  ############################
  def quit(self):
    """Close the connection from our end and quit."""
    logging.info('WebSocketConnection %s: quit signaled', self.websocket)
    self.quit_flag = True
    self.websocket.close(reason='Server signaled quit.')

  ############################
  @asyncio.coroutine
  async def serve_data(self):
    """Start serving on websocket. Assumes we've got our own event loop.
    """
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
  @asyncio.coroutine
  async def get_client_request(self):
    """Get the fields we're interested in having served.
    """
    try:
      message = await self.websocket.recv()
    except websockets.exceptions.ConnectionClosed:
      logging.info('Client closed connection')
      self.quit()
      return

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
    logging.debug('CachedDataServer connection sending: %s', send_message)

    try:
      await self.websocket.send(send_message)
      logging.debug('Websocket sent data, awaiting ready...')
      ready_message = await self.websocket.recv()
      if not ready_message == 'ready':
        logging.error('CachedDataServer connection "ready" message: "%s"',
                      ready_message)
      logging.debug('Websocket got ready...')
    except websockets.exceptions.ConnectionClosed:
      logging.info('Client closed connection')
      self.quit()
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
      logging.debug('Requesting field: %s, %g secs.', field_name,
                    fields[field_name].get('seconds', 0))

    # Keep track of the latest timestamp we've sent to a client, so we
    # only ever send new data.
    latest_timestamp_sent = {field_name: 0 for field_name in fields}

    while not self.quit_flag:
      # logging.warning('Serving...')
      now = time.time()
      results = {}
      for field_name, field_spec in fields.items():
        back_seconds = field_spec.get('seconds', 0)
        field_cache = self.cache.get(field_name, None)
        if field_cache is None:
          logging.debug('No cached data for %s', field_name)
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
        logging.debug('CachedDataServer connection sending %d bytes',
                      len(send_message))
        try:
          await self.websocket.send(send_message)
          logging.debug('Websocket sent data, awaiting ready...')
          ready_message = await self.websocket.recv()
          if not ready_message == 'ready':
            logging.error('CachedDataServer connection non "ready" message: '
                          '"%s"', ready_message)
          logging.debug('Websocket got ready...')
        except websockets.exceptions.ConnectionClosed:
          logging.info('Client closed connection')
          self.quit()
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



################################################################################
class CachedDataServer:
  """Class that caches field:value pairs passed to it in either a
  DASRecord or a simple dict. It also establishes a websocket server
  at the specified host:port name and serves the cached values to
  clients that connect via a websocket.

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
  """

  ############################
  def __init__(self, websocket, interval=1, event_loop=None):
    try:
      self.host, port = websocket.split(':')
      self.port = int(port)
    except ValueError as e:
      logging.error('websocket argument format must be host:port')
      raise e

    self.interval = interval
    self.cache = {}
    self.cache_lock = threading.Lock()

    # List where we'll store our websocket connections so that we can
    # keep track of which are still open, and signal them to close
    # when we're done.
    self._connections = []
    self._connection_lock = threading.Lock()

    # If we've received an event loop, use it
    self.event_loop = event_loop or asyncio.get_event_loop()
    if event_loop:
      asyncio.set_event_loop(event_loop)

    self.quit_flag = False

    # Fire up the thread that's going to the websocket server in our
    # event loop. Calling quit() it will close any remaining
    # connections and stop the event loop, terminating the server.
    self.server_thread = threading.Thread(target=self._run_websocket_server,
                                          daemon=True)
    self.server_thread.start()

  ############################
  def cache_record(self, record):
    """Add the passed record to the cache.

    Expects passed records to either be DASRecords or simple dicts. If
    type(record) is dict, expect it to be in one of the following
    formats:

       {field_name: value,    # use default timestamp of 'now'
        field_name: value,
        ...
       }
    or
       {field_name: [(timestamp, value), (timestamp, value),...],
        field_name: [(timestamp, value), (timestamp, value),...],
        ...
       }
    """
    logging.debug('CachedDataServer.cache_record() received: %s', record)
    if not record:
      logging.debug('CachedDataServer.cache_record() received empty record.')
      return
    if not type(record) in [DASRecord, dict]:
      logging.error('CachedDataServer.cache_record() received record of type '
                    '"%s" - must be either dict or DASRecord', type(record))
      return

    #logging.warning('Caching record')

    # If we've been passed a DASRecord, the field:value pairs are in a
    # field called, uh, 'fields'; if we've been passed a dict, we'll
    # assume that the field:value pairs are the top level.
    if type(record) is DASRecord:
      fields = record.fields
      default_timestamp = record.timestamp
    else:
      fields = record
      default_timestamp = time.time()

    # Add values from record to cache
    with self.cache_lock:
      for field, value in fields.items():
        if not field in self.cache:
          self.cache[field] = []

        if type(value) is list:
          # Okay, for this field we have a list of values - iterate through
          for val in value:
            # If element in the list is itself a list or a tuple,
            # we'll assume it's a (timestamp, value) pair. Otherwise,
            # use the default timestamp of 'now'.
            if type(val) in [list, tuple]:
              self.cache[field].append(val)
            else:
              self.cache[field].append((default_timestamp, value))
        else:
          # If type(value) is *not* a list, assume it's the value
          # itself. Add it using the default timestamp.
          self.cache[field].append((default_timestamp, value))

  ############################
  def cleanup(self, oldest):
    """Remove any data from cache with a timestamp older than 'oldest' seconds.
    """
    logging.debug('Cleaning up cache')
    with self.cache_lock:
      for field in self.cache:
        value_list = self.cache[field]
        while value_list and value_list[0][0] < oldest:
          value_list.pop(0)

  ############################
  def _run_websocket_server(self):
    """Start serving on the specified websocket.
    """
    logging.info('Starting WebSocketServer')
    try:
      self.websocket_server = websockets.serve(
        ws_handler=self._serve_websocket_data,
        host=self.host, port=self.port,
        loop=self.event_loop)

      # If event loop is already running, just add server to task list
      if self.event_loop.is_running():
        asyncio.ensure_future(self.websocket_server, loop=self.event_loop)

      # Otherwise, fire up the event loop now
      else:
        self.event_loop.run_until_complete(self.websocket_server)
        self.event_loop.run_forever()
    except OSError as e:
      logging.fatal('Failed to open websocket %s:%s: %s',
                    self.host, self.port, str(e))
      raise e

  ############################
  def quit(self):
    """Exit the loop and shut down all loggers.
    """
    self.quit_flag = True

    # Close any connections
    with self._connection_lock:
      for connection in self._connections:
        connection.quit()
    logging.info('WebSocketServer closed')

    # Stop the event loop that's serving connections
    self.event_loop.stop()

    # Wait for thread that's running the server to finish
    self.server_thread.join()

  ############################
  """Top-level coroutine for running CachedDataServer."""
  @asyncio.coroutine
  async def _serve_websocket_data(self, websocket, path):
    logging.info('New data websocket client attached: %s', path)

    # Here is where we see the anomalous behavior - when constructed
    # directly, self.cache is as it should be: a shared cache. But
    # when invoked indirectly, e.g. as part of a listener via
    #
    #    listener = ListenerFromLoggerConfig(config)
    #    proc = multiprocessing.Process(target=listener.run, daemon=True)
    #    proc.start()
    # 
    # then self.cache always appears ins in its initial (empty) state.
    connection = WebSocketConnection(websocket, self.cache, self.cache_lock,
                                     self.interval)

    # Stash the connection so we can tell it to exit when we receive a
    # quit(). But first do some cleanup, getting rid of old
    # connections that have closed.
    with self._connection_lock:
      index = 0
      while index < len(self._connections):
        if self._connections[index].closed():
          logging.info('Disposing of closed connection.')
          self._connections.pop(index)
        else:
          index += 1
      # Now add the new connection
      self._connections.append(connection)

    await connection.serve_data()

################################################################################
################################################################################
if __name__ == '__main__':
  import argparse

  from logger.readers.composed_reader import ComposedReader
  from logger.readers.network_reader import NetworkReader
  from logger.transforms.parse_nmea_transform import ParseNMEATransform
  from logger.utils import nmea_parser

  parser = argparse.ArgumentParser()
  parser.add_argument('--network', dest='network', required=True,
                      action='store',
                      help='Comma-separated list of network ports to listen '
                      'for data on, e.g. :6221,:6224')

  parser.add_argument('--websocket', dest='websocket', required=True,
                      action='store',
                      help='Host:port on which to serve data')

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
                      type=float, default=480,
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


  readers = [NetworkReader(network=network)
             for network in args.network.split(',')]
  transform = ParseNMEATransform(
    message_path=args.parse_nmea_message_path,
    sensor_path=args.parse_nmea_sensor_path,
    sensor_model_path=args.parse_nmea_sensor_model_path)

  reader = ComposedReader(readers=readers, transforms=[transform])
  writer = CachedDataServer(args.websocket, args.interval)

  # Every N seconds, we're going to detour to clean old data out of cache
  next_cleanup_time = time.time() + args.cleanup_interval

  # Loop, reading data and writing it to the cache
  try:
    while True:
      record = reader.read()
      logging.debug('Got record: %s', record)

      # If, for some reason, we get empty record try again
      writer.cache_record(record)

      # Is it time for next cleanup?
      now = time.time()
      if now > next_cleanup_time:
        writer.cleanup(now - args.back_seconds)
        next_cleanup_time = now + args.cleanup_interval
  except KeyboardInterrupt:
    logging.warning('Received KeyboardInterrupt - shutting down')
    writer.quit()
