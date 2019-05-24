#!/usr/bin/env python3
"""NOTE: See below for mysterious cache behavior when invoked via
logger_manager.py

Accept data in DASRecord or dict format via the cache_record() method,
then serve it to anyone who connects via a websocket. A
CachedDataServer can be instantiated by running this script from the
command line and providing one or more UDP ports on which to listen
for timestamped text data that it can parse into key:value pairs. It
may also be instantiated as part of a CachedDataWriter that can be
invoked on the command line via the listen.py script of via a
configuration file.

The following direct invocation of this script

    logger/utils/cached_data_server.py \
      --network :6225 \
      --websocket :8766 \
      --back_seconds 480 \
      --v

says to

1. Listen on the UDP port specified by --network for JSON-encoded,
   timestamped, field:value pairs. (See the definition for cache_record(),
   below for formats understood.)

2. Store the received data in an in-memory cache, retaining the most
   recent 480 seconds for each field.

3. Wait for clients to connect to the websocket at port 8766 and serve
   them the requested data. Web clients may issue JSON-encoded
   requests of the following formats (see the definition of
   serve_requests() for insight):

   {'type':'fields'}   - return a list of fields for which cache has data

   {'type':'subscribe',
    'fields':{'field_1':{'seconds':50},
              'field_2':{'seconds':0},
              'field_3':{'seconds':-1}}}

       - subscribe to updates for field_1, field_2 and field_3. Allowable
         values for 'seconds':

            0  - provide only new values that arrive after subscription
           -1  - provide the most recent value, and then all future new ones
           num - provide num seconds of back data, then all future new ones
         
         If 'seconds' is missing, use '0' as the default.

   {'type':'ready'}

       - indicate that client is ready to receive the next set of updates
         for subscribed fields.

   {'type':'publish', 'data':{'timestamp':1555468528.452,
                              'fields':{'field_1':'value_1',
                                        'field_2':'value_2'}}}

       - submit new data to the cache (an alternative way to get data
         in that doesn't, e.g. have the same record size limits as a
         UDP packet).
   
A CachedDataServer may also be created by invoking the listen.py
script and creating a CachedDataWriter (which is just a wrapper around
CachedDataServer). It may be invoked with the same options, and has
the added benefit that you can have your server take data from a wider
variety of sources (by using a LogfileReader, DatabaseReader,
RedisReader or the like):

    logger/listener/listen.py \
      --network :6221,:6224 \
      --parse_definition_path local/devices/*.yaml,test/sikuliaq/devices.yaml \
      --transform_parse \
      --write_cached_data_writer :8766

This command  line creates  a CachedDataWriter that  reads timestamped
NMEA sentences, parses them into  field:value pairs, then stores them,
as above, in in-memory cached to be served to connected webclients.

Note that the listen.py script currently provides no way to override
the default values for back_seconds (480) and cleanup (60). But a
contributor who wished could easily add the appropriate flags to the
listen.py script.

Finally, it may be incorporated (again, within its CachedDataWriter
wrapper) into a logger via a configuration file:

    logger/listener/listen.py --config_file data_server_config.yaml

where data_server_config.yaml contains:

readers:
- class: NetworkReader
  kwargs: {network: ':6221'}
- class: NetworkReader
  kwargs: {network: ':6224'}
transforms:
- class: ParseTransform
writers:
- class: CachedDataWriter
  kwargs:
    back_seconds: 480
    cleanup: 60
     websocket: ':8766'

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
import pprint
import sys
import threading
import time
import websockets

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

############################
def cache_record(record, cache, cache_lock):
  """Add the passed record to the passed cache.

  Expects passed records to be in one of two formats:

  1) DASRecord

  2) a dict encoding optionally a source data_id and timestamp and a
     mandatory 'fields' key of field_name: value pairs. This is the format
     emitted by default by ParseTransform:

     {
       'data_id': ...,    # optional
       'timestamp': ...,  # optional - use time.time() if missing
       'fields': {
         field_name: value,
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
       'data_id': ...,  # optional
       'fields': {
          field_name: [(timestamp, value), (timestamp, value),...],
          field_name: [(timestamp, value), (timestamp, value),...],
          ...
       }
     }
  """
  logging.debug('cache_record() received: %s', record)
  if not record:
    logging.debug('cache_record() received empty record.')
    return

  # If we've been passed a DASRecord, the field:value pairs are in a
  # field called, uh, 'fields'; if we've been passed a dict, look
  # for its 'fields' key.
  if type(record) is DASRecord:
    record_timestamp = record.timestamp
    fields = record.fields
  elif type(record) is dict:
    record_timestamp = record.get('timestamp', time.time())
    fields = record.get('fields', None)
    if fields is None:
      logging.error('Dict record passed to cache_record() has no '
                    '"fields" key, which either means it\'s not a dict '
                    'you should be passing, or it is in the old "field_dict" '
                    'format that assumes key:value pairs are at the top '
                    'level.')
      logging.error('The record in question: %s', str(record))
      return
  else:
    logging.warning('Received non-DASRecord, non-dict input (type: %s): %s',
                      type(record), record)
    return

  # Add values from record to cache
  with cache_lock:
    for field, value in fields.items():
      if not field in cache:
        cache[field] = []

      if type(value) is list:
        # Okay, for this field we have a list of values - iterate through
        for val in value:
          # If element in the list is itself a list or a tuple,
          # we'll assume it's a (timestamp, value) pair. Otherwise,
          # use the default timestamp of 'now'.
          if type(val) in [list, tuple]:
            cache[field].append(val)
          else:
            cache[field].append((record_timestamp, value))
      else:
        # If type(value) is *not* a list, assume it's the value
        # itself. Add it using the default timestamp.
        cache[field].append((record_timestamp, value))


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
  async def send_json_response(self, response, is_error=False):
    logging.debug('CachedDataServer sending %d bytes',
                  len(json.dumps(response)))
    await self.websocket.send(json.dumps(response))
    if is_error:
      logging.warning(response)

  ############################
  @asyncio.coroutine
  async def serve_requests(self):
    """Wait for requests and serve data, if it exists, from
    cache. Requests are in JSON with request type encoded in
    'request_type' field. Recognized request types are:

    fields - return a (JSON encoded) list of fields for which cache
        has data.

    publish - look for a field called 'data' and expect its value to
        be a dict containing data in one of the formats accepted by
        cache_record().

    subscribe - look for a field called 'fields' in the request whose
        value is a dict of the format

          {field_name:{seconds:600}, field_name:{seconds:0},...}

        May also have a field called 'interval', specifying how often
        server should provide updates. Will default to what was
        specified on command line with --interval flag (which itself
        defaults to 1 second intervals).

        Begin serving JSON messages of the format
          {
            field_name: [(timestamp, value), (timestamp, value),...],
            field_name: [(timestamp, value), (timestamp, value),...],
            field_name: [(timestamp, value), (timestamp, value),...],
          }

        Initially provide the number of seconds worth of back data
        requested, and on subsequent calls, return all data that have
        arrived since last call.

        NOTE: if the 'seconds' field is -1, server will only ever provide
        the single most recent value for the relevant field.

    ready - client has processed the previous data message and is ready
        for more.

    """
    # A map from field_name:latest_timestamp_sent. If
    # latest_timestamp_sent is -1, then we'll always send just the
    # most recent value we have for the field, regardless of how many
    # there are, or whether we've sent it before.
    field_timestamps = {}
    interval = self.interval # Use the default interval, uh, by default

    while not self.quit_flag:
      now = time.time()
    
      try:
        logging.debug('Waiting for client')
        raw_request = await self.websocket.recv()
        request = json.loads(raw_request)
      except json.JSONDecodeError:
        await self.send_json_response(
          {'status':400, 'error':'received unparseable JSON'},
          is_error=True)
        logging.warning('unparseable JSON: %s', raw_request)
        continue
      except websockets.exceptions.ConnectionClosed:
        logging.info('Client closed connection')
        self.quit()
        continue

      # Make sure we've received a dict
      if not type(request) is dict:
        await self.send_json_response(
          {'status':400, 'error':'non-dict request received'},
          is_error=True)

      # Make sure request dict has a 'type' field
      elif not 'type' in request:
        await self.send_json_response(
          {'status':400, 'error':'no "type" field found in request'},
          is_error=True)

      # Let's see what type of request it is
      
      # Send client a list of the variable names we're able to serve.
      elif request['type'] == 'fields':
        logging.debug('fields request')
        await self.send_json_response(
          {'type':'fields', 'status':200, 'data':list(self.cache.keys())})

      # Client wants to publish to cache and provides a dict of data
      elif request['type'] == 'publish':
        logging.debug('publish request')
        data = request.get('data', None)
        if data is  None:
          await self.send_json_response(
            {'type':'publish', 'status':400,
             'error':'no data field found in request'},
             is_error=True)
        elif type(data) is not dict:
          await self.send_json_response(
            {'type':'publish', 'status':400,
             'error':'request has non-dict data field'},
             is_error=True)
        else:
          cache_record(data, self.cache, self.cache_lock)
          await self.send_json_response({'type':'publish', 'status':200})

      # Client wants to subscribe, and provides a dict of requested fields
      elif request['type'] == 'subscribe':
        logging.debug('subscribe request')
        # Have they given us a new subscription interval?
        requested_interval = request.get('interval', None)
        if requested_interval is not None:
          try:
            interval = float(requested_interval)
          except ValueError:
            await self.send_json_response(
              {'type':'subscribe', 'status':400,
               'error':'non-numeric interval requested'},
              is_error=True)
            continue

        requested_fields = request.get('fields', None)
        if not requested_fields:
          await self.send_json_response(
            {'type':'subscribe', 'status':400,
             'error':'no fields found in subscribe request'},
            is_error=True)
          continue

        # Parse out request field names and number of back seconds
        # requested. Encode that as 'last timestamp sent', unless back
        # seconds == -1. If -1, save it as -1, so that we know we're
        # always just sending the the most recent field value.
        field_timestamps = {}
        for field_name, field_spec in requested_fields.items():
          if not type(field_spec) is dict:
            back_seconds = 0
          else:
            back_seconds = field_spec.get('seconds', 0)
          if back_seconds == -1:
            field_timestamps[field_name] = -1
          else:
            field_timestamps[field_name] = time.time() - back_seconds

        # Let client know request succeeded
        await self.send_json_response({'type':'subscribe', 'status':200})

      # Client just letting us know it's ready for more. If there are
      # fields that have been requested, send along any new data for
      # them.
      elif request['type'] == 'ready':
        logging.debug('Websocket got ready...')
        if not field_timestamps:
          await self.send_json_response(
            {'type':'ready', 'status':400,
             'error':'client ready, but no data requested.'},
            is_error=True)
          continue

        results = {}
        for field_name, latest_timestamp in field_timestamps.items():
          field_cache = self.cache.get(field_name, None)
          if field_cache is None:
            logging.debug('No cached data for %s', field_name)
            continue

          # If no data for requested field, skip.
          if not field_cache or not field_cache[-1]:
            continue

          # If special case -1, they want just single most recent
          # value, then future results. Grab last value, then set its
          # timestamp as the last one we've seen.
          elif latest_timestamp == -1:
            last_value = field_cache[-1]
            results[field_name] = [ last_value ]
            field_timestamps[field_name] = last_value[0] # ts of last value

          # Otherwise - if no data newer than the latest
          # timestamp we've already sent, skip,
          elif not field_cache[-1][0] > latest_timestamp:
            continue

          # Otherwise, copy over records arrived since
          # latest_timestamp and update the latest_timestamp sent
          # (first element of last pair in field_cache).
          else:
            results[field_name] = [pair for pair in field_cache if
                                   pair[0] > latest_timestamp]
            if field_cache:
              field_timestamps[field_name] = field_cache[-1][0]

        logging.debug('Websocket results: %s...', str(results)[0:100])
        
        # Package up what results we have (if any) and send them off
        await self.send_json_response({'type':'data', 'status':200,
                                       'data':results})

        # New results or not, take a nap before trying to fetch more results
        elapsed = time.time() - now
        time_to_sleep = max(0, interval - elapsed)
        logging.debug('Sleeping %g seconds', time_to_sleep)
        await asyncio.sleep(time_to_sleep)  

      # If unrecognized request type - whine, then iterate
      else:
        await self.send_json_response(
          {'status':400,
           'error':'unrecognized request type: %s' % request_type},
            is_error=True)

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
    """Add the passed record to the cache."""
    cache_record(record, self.cache, self.cache_lock)

  ############################
  def cleanup(self, oldest):
    """Remove any data from cache with a timestamp older than 'oldest'
    seconds, but keep at least one (most recent) value.
    """
    logging.debug('Cleaning up cache')
    with self.cache_lock:
      for field in self.cache:
        value_list = self.cache[field]
        while value_list and len(value_list) > 1 and value_list[0][0] < oldest:
          value_list.pop(0)

  ############################
  def _run_websocket_server(self):
    """Start serving on the specified websocket.
    """
    logging.info('Starting WebSocketServer %s:%s', self.host, self.port)
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
          logging.debug('Disposing of closed connection.')
          self._connections.pop(index)
        else:
          index += 1
      # Now add the new connection
      self._connections.append(connection)

    # If client disconnects, tell connection to quit
    try:
      await connection.serve_requests()
    except websockets.ConnectionClosed:
      logging.warning('client disconnected')
      connection.quit()

################################################################################
################################################################################
if __name__ == '__main__':
  import argparse

  from logger.readers.composed_reader import ComposedReader
  from logger.readers.network_reader import NetworkReader
  from logger.transforms.from_json_transform import FromJSONTransform
  from logger.utils import record_parser

  parser = argparse.ArgumentParser()
  parser.add_argument('--websocket', dest='websocket', required=True,
                      action='store',
                      help='Host:port on which to serve data')

  parser.add_argument('--network', dest='network', default=None, action='store',
                      help='Comma-separated list of network ports to listen '
                      'for data on, e.g. :6221,:6224')

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

  # Only create reader(s) if they've given us a network to read from;
  # otherwise, count on data coming from websocket publish
  # connections.
  if args.network:
    readers = [NetworkReader(network=network)
               for network in args.network.split(',')]
    transform = FromJSONTransform()
    reader = ComposedReader(readers=readers, transforms=[transform])
    
  server = CachedDataServer(args.websocket, args.interval)

  # Every N seconds, we're going to detour to clean old data out of cache
  next_cleanup_time = time.time() + args.cleanup_interval

  # Loop, reading data and writing it to the cache
  try:
    while True:
      if args.network:
        record = reader.read()
        logging.debug('Got record: %s', record)

        # If, for some reason, we get empty record try again
        server.cache_record(record)
      else:
        time.sleep(args.interval)

      # Is it time for next cleanup?
      now = time.time()
      if now > next_cleanup_time:
        server.cleanup(now - args.back_seconds)
        next_cleanup_time = now + args.cleanup_interval
  except KeyboardInterrupt:
    logging.warning('Received KeyboardInterrupt - shutting down')
    server.quit()
