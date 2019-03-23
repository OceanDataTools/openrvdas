#!/usr/bin/env python3
"""A server that acts as a pubsub clearinghouse for status/error/data
messages. Clients connect via a websocket and specify what message
channels they're interested in.

There are (will be?) rudimentary hooks for JWT authentication so that
only authorized clients can connect or (eventually) can perform more
sensitive operations such as (maybe some day) request configuration
changes.

At the moment it's written to assume a Redis backing server for the
pubsub service.

TODO: At the moment, expects Redis commands in simple text
format. Should really take them as JSON, shouldn't it

TODO: Add Redis stream functions, as documented here:
https://aioredis.readthedocs.io/en/v1.2.0/mixins.html. Currently
implemented functions are for simple key get/set/mget/mset and pubsum
channels, but streams seem more powerful, especially for getting past
data, e.g. for data displays.
"""
import aioredis
import asyncio
import copy
import json
import logging
import subprocess
import sys
import threading
import websockets

# Add project path for local imports
#from os.path import dirname, realpath; sys.path.append(dirname(dirname(realpath(__file__))))
#from server.websocket_server import WebsocketServer

DEFAULT_WEBSOCKET = '0.0.0.0:8766'
DEFAULT_REDIS_SERVER = 'localhost:6379'

################################################################################# Helper function we can use all over the place
def parse_host_spec(host_spec, default_host=None, default_port=None):
  """Parse a host:port string into separate host and port and return as tuple.

  host_spec  - a host:port string to be parsed.

  default_host - the hostname to be used if host_spec is of form ":port";
        typically this would be "localhost".

  default_port - port to be used if the host_spec is of form "hostname" and
        is missing a ":"
  """
  if not ':' in host_spec: # use as hostname with default port
    if default_port is None:
      raise ValueError('Unable to parse "%s" into host:port and no default '
                       'port specified' % host_spec)
    return (host_spec, default_port)

  host, port_str = host_spec.split(':')
  host = host or default_host
  if not host:  # no host, then none specified and no default
    raise ValueError('Unable to parse host specification "%s" into host:port '
                     'and no default host specified' % host_spec)
  try:
    port = int(port_str or default_port)
  except ValueError:
    raise ValueError('Unable to parse host specification "%s" into host:port'
                     % host_spec)

  return (host, port)

################################################################################
class StatusServer:
  ############################
  def __init__(self, websocket=None, redis=None,
               auth_token=None, use_ssl=False, event_loop=None):
    """
    websocket - websocket [host]:[port] on which to serve connections. If
            host or port are omitted, use default from 0.0.0.0:8766.

    redis - [host]:[port] of Redis server to connect to. If host
            or port are omitted, use default from localhost:6379. If host is
            localhost and no server is detected at that address, attempt to
            start one up.

    auth_token - NOT YET IMPLEMENTED. Use this token to authenticate requests
            to add AUTH tokens for other websocket clients.

    use_ssl - if True, try to serve websockets via wss; not fully-implemented

    event_loop - if provided, use this event loop instead of the default.
    """
    self.websocket = websocket or DEFAULT_WEBSOCKET
    self.redis = redis or DEFAULT_REDIS_SERVER
    self.event_loop = event_loop or asyncio.get_event_loop()

    # If we end up starting our own Redis server, here's where we
    # stash the process (so we can kill it when we're done).
    self.redis_proc = None

    # Where we'll store websocket connection, Redis connection,
    # etc. of the clients that connect
    self.client_map = {}
    self.client_lock = threading.Lock()

    # As-yet-unused security stuff
    self.auth_token = auth_token
    self.ssl_context = None
    if use_ssl:
      self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

    # Instantiate websocket server
    self.event_loop.run_until_complete(self._start_websocket_server())

    # Start Redis server if it doesn't exist
    self.event_loop.run_until_complete(self._start_redis_server())

  ############################
  async def _start_websocket_server(self):
    """Parse host:port of websocket spec and async ensure server future.
    """
    default_host, default_port = parse_host_spec(DEFAULT_WEBSOCKET)
    host, port = parse_host_spec(self.websocket, default_host, default_port)
    try:
      ws_server = websockets.serve(self._handler, host, port,
                                   ssl=self.ssl_context)
      asyncio.ensure_future(ws_server, loop=self.event_loop)
      logging.info('Websocket server at %s:%d started.', host, port)
    except OSError as e:
      raise OSError('Failed to open websocket %s:%d  %s' % (host, port, str(e)))

  ############################
  async def _start_redis_server(self):
    """Try to connect to specified Redis server. If it doesn't exist, try
    to start one.
    """
    # First, parse to make sure it's a valid host:port
    default_host, default_port = parse_host_spec(DEFAULT_REDIS_SERVER)
    host, port = parse_host_spec(self.redis, default_host, default_port)

    # If we're able to connect to a server at the specified address,
    # we don't need to start one of our own.
    try:
      await aioredis.create_redis('redis://' + self.redis)
      return
    except OSError:
      logging.info('Unable to connect to Redis server at %s; will try '
                   'to start one of our own at that address.', self.redis)

    # If we're here, we failed to connect to a Redis server because we
    # think it doesn't exist. Try to start it, if we can.
    if host and not host == 'localhost':
      raise ValueError('Can only start Redis on localhost, not %s' % self.redis)
    try:
      cmd_line = ['/usr/bin/env', 'redis-server', '--port %d' % port]
      self.redis_proc = subprocess.Popen(cmd_line, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
      logging.info('Redis server at %s:%d started.', host, port)
    except OSError as e:
      raise OSError('Failed to start Redis server at %s: %s' % (self.redis, e))

  ############################
  def run(self):
    #asyncio.get_event_loop().set_debug(True)
    asyncio.get_event_loop().run_forever()

  ############################
  async def _handler(self, websocket, path):
    client_id = await self._register_websocket_client(websocket, path)
    logging.warning('Websocket client %d has connected', client_id)

    await self._get_messages(client_id)

    # When client disconnects, delete the tasks it was using
    await self._unregister_websocket_client(client_id)
    logging.info('Websocket client %d completed', client_id)

  ############################
  async def _register_websocket_client(self, websocket, path):
    """We've been alerted that a websocket client has connected.
    Register it properly."""

    # A dummy class that lets us compactly create a client namespace
    class WSClient:
      pass

    client = WSClient()
    client.websocket = websocket
    client.redis = await aioredis.create_redis('redis://' + self.redis)
    client.path = path
    client.auth = None
    client.lock = threading.Lock()
    client.tasks = []  # Where we'll stash list of client's async tasks
    client.subscriptions = {}
    with self.client_lock:
      # Get an unused client_id
      client_id = 0
      while client_id in self.client_map:
        client_id += 1
      client.id = client_id
      self.client_map[client_id] = client

    return client_id

  ############################
  async def _unregister_websocket_client(self, client_id):
    """We've been alerted that a websocket client has disconnected.
    Unregister it properly."""
    logging.info('Websocket client %d has disconnected; cleaning up', client_id)
    with self.client_lock:
      if self.client_map and client_id in self.client_map:
        client = self.client_map[client_id]

        # Clean up any of client's unfinished business
        with client.lock:
          for channel_name, task in client.subscriptions.items():
            logging.info('Canceling client %d subscription to %s',
                         client_id, channel_name)
            task.cancel()
          for task in client.tasks:
            logging.info('Canceling client %d task %s', client_id, task)
            task.cancel()
        del self.client_map[client_id]
      else:
        logging.warning('Websocket client %d has disconnected, but no '
                        'record of it having connected?!?', client_id)

  ############################
  async def _get_messages(self, client_id):
    """Consume messages from websocket, parse, and pass along to Redis."""
    try:
      websocket = self.client_map[client_id].websocket
      async for message in websocket:
        logging.debug('Websocket server received message: ' + message)
        await self._process_message(message, client_id)

    except:
      logging.info('Websocket client %d connection lost', client_id)

  ############################
  async def _process_message(self, message, client_id):
    """Parse and process a message we've received from websocket."""

    # Authenticate (hah!), if needed, then pass to Redis. No,
    # authentication isn't implemented yet.

    ##########
    # Set
    if message.find('set ') == 0:
      try:
        s, key, value = message.split(sep=' ', maxsplit=2)
      except ValueError:
        logging.error('Bad set command: "%s"', message)
        return

      # Don't let anyone mess with map while we're fetching client
      with self.client_lock:
        client = self.client_map[client_id]

      with client.lock:
        ch = await client.redis.set(key, value)
      logging.info('  Done setting value[%s] = %s', key, value)

    ##########
    # Get
    elif message.find('get ') == 0:
      try:
        s, key = message.split(sep=' ')
      except ValueError:
        logging.error('Bad get command: "%s"', message)
        return

      # Don't let anyone mess with map while we're fetching client
      with self.client_lock:
        client = self.client_map[client_id]

      with client.lock:
        value = await client.redis.get(key)
      if value is not None:
        value = value.decode()
      logging.info('  Done getting value[%s] = %s', key, value)
      ws_mesg = {
        'type': 'redis_get',
        'key': key,
        'value': value
      }
      logging.info('Client %d sending websocket message %s', client_id, ws_mesg)
      await client.websocket.send(json.dumps(ws_mesg))

    ##########
    # MSet
    elif message.find('mset ') == 0:
      try:
        s, *key_values = message.split(sep=' ')
      except ValueError:
        logging.error('Bad mset command: "%s"', message)
        return

      # Don't let anyone mess with map while we're fetching client
      with self.client_lock:
        client = self.client_map[client_id]

      with client.lock:
        ch = await client.redis.mset(*key_values)
      logging.info('  Done setting key value pairs: %s', key_values)

    ##########
    # MGet
    elif message.find('mget ') == 0:
      try:
        s, *keys = message.split(sep=' ')
      except ValueError:
        logging.error('Bad mget command: "%s"', message)
        return

      # Don't let anyone mess with map while we're fetching client
      with self.client_lock:
        client = self.client_map[client_id]

      with client.lock:
        values = await client.redis.mget(*keys)
      values = [v.decode() if v is not None else None for v in values]

      logging.info('Done getting values %s = %s', keys, values)
      ws_mesg = {
        'type': 'redis_mget',
        'key': keys,
        'values': values
      }
      logging.info('Client %d sending websocket message %s', client_id, ws_mesg)
      await client.websocket.send(json.dumps(ws_mesg))

    ##########
    # Subscribe
    elif message.find('subscribe ') == 0:
      try:
        sub, *channel_names = message.split(sep=' ')
        logging.warning('Client %d subscribing to channels: %s',
                      client_id, channel_names)
      except ValueError:
        logging.error('Bad subscribe command: "%s"', message)
        return

      # Don't let anyone mess with map while we're fetching client
      with self.client_lock:
        client = self.client_map[client_id]

      # Create a reader for each channel we've subscribed to and stash
      # the tasks so we can await/cancel them as appropriate when
      # done. Do this iteratively, instead of as a comprehension, so
      # we can ignore duplicate subscriptions.
      with client.lock:
        for ch_name in channel_names:
          if ch_name in client.subscriptions:
            logging.info('  Client %d duplicate subscription to %s',
                         client_id, ch_name)
            continue
          ch = await client.redis.subscribe(ch_name)
          task = asyncio.ensure_future(self._channel_reader(client_id, ch[0]))
          client.subscriptions[ch_name] = task
      logging.info('  Done subscribing to %s', channel_names)

    ##########
    # PSubscribe
    elif message.find('psubscribe ') == 0:
      try:
        psub, channel_pattern = message.split(sep=' ')
        logging.info('Client %d psubscribing to channel pattern: %s',
                     client_id, channel_pattern)
      except ValueError:
        logging.error('Bad psubscribe command: "%s"', message)
        return

      # Don't let anyone mess with map while we're fetching client
      with self.client_lock:
        client = self.client_map[client_id]
      # Use psubscribe=True when creating channel reader because
      # messages it will get from Redis will be (channel, message)
      # tuples that need to be split apart.
      with client.lock:
        ch = await client.redis.psubscribe(channel_pattern)
        task = asyncio.ensure_future(self._channel_reader(client_id, ch[0],
                                                          psubscribe=True))
        client.subscriptions[channel_pattern] = task
      logging.info('  Done psubscribing to pattern %s', channel_pattern)

    ##########
    # Unsubscribe
    elif message.find('unsubscribe ') == 0:
      try:
        unsub, *channel_names = message.split(sep=' ')
        logging.warning('Client %d unsubscribing from channels: %s',
                      client_id, channel_names)
      except ValueError:
        logging.error('Bad unsubscribe command: "%s"', message)
        return

      with self.client_lock:
        client = self.client_map[client_id]
      with client.lock:
        # Cancel tasks for each channel we're unsubscribing from
        for ch_name in channel_names:
          task = client.subscriptions.get(ch_name, None)
          if task:
            del client.subscriptions[ch_name]
            await client.redis.unsubscribe(ch_name)
            logging.info('  Client %d unsubscribed from %s', client_id, ch_name)
          else:
            logging.info('Client %d asking to unsubscribe from channel %s, '
                         'but no subscription found.', client_id, ch_name)
          logging.info('Done unsubscribing to %s', channel_names)

    ##########
    # Punsubscribe
    elif message.find('punsubscribe ') == 0:
      try:
        punsub, channel_pattern = message.split(sep=' ')
        logging.info('Client %d punsubscribing from channel pattern: %s',
                     client_id, channel_pattern)
      except ValueError:
        logging.error('Bad punsubscribe command: "%s"', message)
        return

      # Don't let anyone mess with map while we're fetching client
      with self.client_lock:
        client = self.client_map[client_id]
      with client.lock:
        ch = await client.redis.punsubscribe(channel_pattern)
      logging.info('  Done punsubscribing to pattern %s', channel_pattern)

    ##########
    # Publish
    elif message.find('publish ') == 0:
      try:
        pub, ch_name, send_message = message.split(sep=' ', maxsplit=2)
        logging.warning('Client %d sending Redis channel %s message: %s',
                        client_id, ch_name, send_message)
      except ValueError:
        logging.error('Bad publish command: "%s"', message)
        return

      client = self.client_map[client_id]
      await client.redis.publish(ch_name, send_message)
      logging.info('Done publishing to %s', ch_name)

    ##########
    # Unknown command
    else:
      logging.warning('Unknown message received from client %d: %s',
                      client_id, message)

  ############################
  async def _channel_reader(self, client_id, channel, psubscribe=False):
    """Listen on a Redis channel for messages, typically for those
    resulting from a channel subscription request). If
    psubscribe=True, then messages are going to arrive as
    (channel_name, message) tuples.
    """
    logging.info('Client %d reading channel %s', client_id, channel.name)
    client = self.client_map[client_id]
    channel_name = channel.name.decode()
    while await channel.wait_message():
      mesg = await channel.get(encoding='utf-8')
      logging.info('Client %d, channel %s received message %s',
                   client_id, channel_name, mesg)

      # If psubscribe, our message is going to be a pair of byte
      # strings encoding the actual channel that the 'publish'
      # matched, and the message itself.
      if psubscribe:
        matched_channel, message = mesg[0].decode(), mesg[1]
      else:
        matched_channel, message = channel_name, mesg

      ws_mesg = {
        'type': 'redis_pub',
        'channel': matched_channel,
        'message': message,
      }
      logging.info('  Client %d channel %s sending websocket message %s',
                   client_id, channel_name, ws_mesg)
      await client.websocket.send(json.dumps(ws_mesg))
      logging.info('  Client %d channel %s sent websocket message %s',
                   client_id, channel_name, ws_mesg)
    logging.info('Client %d channel %s task completed', client_id, channel_name)

  ############################
  def clients(self):
    """Return a dict mapping client_id->websocket."""
    return self.client_map

################################################################################
if __name__ == '__main__':
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument('--websocket', dest='websocket', action='store', type=str,
                      help='Attempt to open specified [host]:[port] as '
                      'websocket and begin reading/writing data on it.')
  parser.add_argument('--redis', dest='redis', action='store', type=str,
                      help='Attempt to connect connect to or start a Redis '
                      'server at the specified [host]:[port] as websocket '
                      'and begin reading/writing data on it.')
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  # Set logger format and verbosity
  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)
  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  # Create the websocket server, setting up queued senders/receivers
  server = StatusServer(websocket=args.websocket, redis=args.redis)

  # Start websocket server
  try:
    server.run()
  except KeyboardInterrupt:
    logging.warning('Got interrupt')
