#!/usr/bin/env python3
"""A server that acts as a pubsub clearinghouse for status/error/data
messages. Clients connect via a websocket and specify what message
channels they're interested in.

By default will expect websocket clients to feed it with text commands
similar (identical?) to a subset of commands accepted by redis-cli:

  Get/Set
  =======
  get test_k1
   -> {"type": "redis_get", "key": "test_k1", "value": null}

  set test_k1 value1
  get test_k1'
   -> {"type": "redis_get", "key": "test_k1", "value": "value1"}

  MGet/MSet
  =========
  mset test_k1 value1 test_k2 value2 test_k3 value3
  mget test_k1 test_k3 test_k5
   -> {"type": "redis_mget",
       "result": {"test_k1": "value1", "test_k3": "value3", "test_k5": null}}

  Subscribe/Unsubscribe
  =====================
  subscribe ch1 ch2
  unsubscribe ch1 ch2

  Psubscribe/Punsubscribe
  =======================
  psubscribe channel_pattern*
  punsubscribe channel_pattern*

  Publish
  =======
  publish ch1 ch1_test
   -> {"type": "redis_pub", "channel": "ch1", "message": "ch1_test"}')


If started with the --use_json flag, will expect websocket clients to
feed it with JSON strings:

  Get/Set
  =======
  {"type": "get", "key": "test_k1"}
    -> {"type": "redis_get", "key": "test_k1", "value": null}

  {"type": "set", "key": "test_k1", "value": "value1"}

  {"type": "get", "key": "test_k1"}
    ->  {"type": "redis_get", "key": "test_k1", "value": "value1"}

  MGet/MSet
  =======
  {"type": "mset", "values":{"test_k1": "value1",
                            "test_k2": "value2",
                            "test_k3": "value3"} }

  {"type": "mget", "keys": ["test_k1", "test_k3", "test_k5"]}
    ->  {"type": "redis_mget",
         "result": {"test_k1": "value1", "test_k3": "value3", "test_k5": null}}

  Subscribe/Unsubscribe
  =====================
  {"type": "subscribe", "channels":["ch1", "ch2"]}
    or
  {"type": "subscribe", "channel": "ch1"}

  {"type": "unsubscribe", "channels":["ch1", "ch2"]}
    or
  {"type": "unsubscribe", "channel": "ch1"}


  Psubscribe/Punsubscribe
  =====================
  {"type": "psubscribe", "channel_pattern": "ch*"}

  {"type": "punsubscribe", "channel_pattern": "ch*"}

  Publish
  =======
  {"type": "publish", "channel": "ch3", "message": "ch3_test"}

  Published messages will be returned in JSON of the format:

   -> {"type": "redis_pub", "channel": "ch3", "message": "ch3_test"}


Authentication
==============
NOTE: authentication only works when --use_json is specified.

Authentication is VERY PRIMITIVE at the moment. Authentication is
enabled if a master auth_token is passed in on the command line
(TODO: allow reading master auth_token and user auth_tokens from
protected file).

Initially, when invoked like this, all requests must include the token
or will be discarded as "unauthorized":

  {"type":"get", "key":"test_k1", "auth_token": "3fAEF4erfae4$A"}

Specific users may be authorized for specific operations by means of
an "auth" request:

  {"type":"auth", "auth_token": "3fAEF4erfae4$A",
   "user":"user1", "user_auth_token":"eEfe44fae4", "commands": ["set", "get"]}

The above request adds permission for user "user1" to perform commands
"set" and "get". The first time user1 wishes to perform one of those
commands on a client, they will need to include their user name and
their own auth_token:

  {"type":"set", "key":"test_k5", "value": "value5",
   "user":"user1", "auth_token": "eEfe44fae4"}

The server will cache the fact that this client connection is owned by
user1, and will allow future requests that are authorized for user1 on
this connection without the need for an auth_token:

  {"type":"get", "key":"test_k6"}

THIS LAST BIT MAY BE A BAD IDEA - I DON'T REALLY KNOW.

====

At the moment it's written to assume a Redis backing server for the
pubsub service.

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
import pathlib
import pprint
import ssl
import subprocess
import sys
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
class PubSubServer:
  ############################
  def __init__(self, websocket=None, redis=None, auth_token=None,
               use_json=False, use_ssl=False, event_loop=None):
    """
    websocket - websocket [host]:[port] on which to serve connections. If
            host or port are omitted, use default from 0.0.0.0:8766.

    redis - [host]:[port] of Redis server to connect to. If host
            or port are omitted, use default from localhost:6379. If host is
            localhost and no server is detected at that address, attempt to
            start one up.

    auth_token - Use this token to authenticate requests to add AUTH
            tokens for other websocket clients.

    use_json - if True, expect websocket clients to send requests in JSON
            format.

    use_ssl - if True, try to serve websockets via wss; not fully-implemented

    event_loop - if provided, use this event loop instead of the default.
    """
    self.websocket = websocket or DEFAULT_WEBSOCKET
    self.redis = redis or DEFAULT_REDIS_SERVER
    self.use_json = use_json
    self.event_loop = event_loop or asyncio.get_event_loop()

    # If we end up starting our own Redis server, here's where we
    # stash the process (so we can kill it when we're done).
    self.redis_proc = None

    # Where we'll store websocket connection, Redis connection,
    # etc. of the clients that connect
    self.client_map = {}
    self.client_lock = asyncio.Lock()

    # Authentication stuff. We use self.auth_token as the One True
    # Token that, if specified, is authorized to do anything,
    # including adding authorization for other users to use their own
    # tokens for specified operations.
    self.auth_token = auth_token

    # We store user authentication stuff in self.auth in dict:
    #   user: {'auth_token':token, 'commands': set(authorized commands)}
    #
    # When a client connects and gives us appropriate 'user' and
    # 'auth_token' fields in a request, we check whether the command
    # they're asking for (publish, subscribe, etc.) is in their
    # commands set. If it is, we not only execute the command, but we
    # cache that permission so that the client. can perform that
    # command again in the future without having to send along user
    # and auth_token.
    self.auth = {}

    self.ssl_context = None
    if use_ssl:
      self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
      #self.ssl_context.load_cert_chain(
      #  pathlib.Path(__file__).with_name('certificate goes here'))

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
      server = await aioredis.create_redis('redis://' + self.redis)
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
    logging.info('Websocket client %d has connected', client_id)

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
    client.lock = asyncio.Lock()
    client.tasks = []  # Where we'll stash list of client's async tasks
    client.subscriptions = {}
    async with self.client_lock:
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
    async with self.client_lock:
      if self.client_map and client_id in self.client_map:
        client = self.client_map[client_id]

        # Clean up any of client's unfinished business
        async with client.lock:
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
        if self.use_json:
          await self._process_json_message(message, client_id)
        else:
          await self._process_text_message(message, client_id)

    except:
      logging.info('Websocket client %d connection lost', client_id)

  ############################
  async def _check_auth(self, client_id, json_mesg):
    """Check whether the json_request is an authorized operation."""

    # First, see if they've explicitly handing us an auth token.
    auth_token = json_mesg.get('auth_token', None)
    user = json_mesg.get('user', None)
    command = json_mesg.get('type', None)

    # Is it the One True Token? If so, they can do whatever they want
    if auth_token == self.auth_token:
      return True

    #logging.warning('Auth structure:\n%s', pprint.pformat(self.auth))

    if auth_token:
      #logging.warning('Testing for request auth')
      # If we've got an auth token and it's not the One True Token,
      # try to find a user_auth to go with it.
      if not user:
        return False
      user_auth = self.auth.get(user, None)
      if not user_auth:
        return False
      if not auth_token == user_auth.get('auth_token', None):
        return False

      # So far so good. Now let's see what they want to do, and
      # whether it's an authorized command.
      auth_commands = user_auth.get('commands', [])
      if not command in auth_commands:
        return False

      #logging.warning('Request is authorized')

      # If they're allowed to do it, give the okay. Should we also
      # cache that this particular client is now allowed to do these
      # operations, regardless of whether they've passed us a token?
      async with self.client_lock:
        client = self.client_map.get(client_id)
      async with client.lock:
        #logging.warning('Got client lock')
        if not client.auth:
          #logging.warning('Adding client auth')
          client.auth = {'user':user,
                         'auth_token':auth_token,
                         'commands':set(auth_commands)}
      #logging.warning('Cached request authorization')
      return True

    # They've not passed us an auth_token; let's see if we've already
    # authorized them.
    #logging.warning('Testing for client auth')
    client = self.client_map.get(client_id, None)
    if not client or not client.auth:
      return False
    if not command in client.auth.get('commands', []):
      return False
    #logging.warning('Client is authorized')
    return True

  ############################
  async def _process_json_message(self, message, client_id):
    """Parse and process a JSON message we've received from websocket."""

    try:
      json_mesg = json.loads(message)
    except json.decoder.JSONDecodeError:
      logging.error('Unable to decode JSON string: "%s"', message)
      return

    # Have we been initialized with an auth token? If so, only allow
    # authorized users to do stuff.
    if self.auth_token and not await self._check_auth(client_id, json_mesg):
      logging.info('Unauthorized request: %s', json_mesg)
      return

    mesg_type = json_mesg.get('type', None)
    if mesg_type is None:
      raise ValueError('Bad JSON message: no "type" field')

    ##########
    # Auth - add authentication for a user.
    if mesg_type == 'auth':
      # If we're here, we're allowed to do 'auth' commands. Scary,
      # isn't it?
      user = json_mesg['user']
      user_auth_token = json_mesg['user_auth_token']
      commands = json_mesg['commands']
      self.auth[user] = {'auth_token':user_auth_token, 'commands':commands}

    # Set
    elif mesg_type == 'set':
      try:
        await self._redis_set(client_id, json_mesg['key'], json_mesg['value'])
      except ValueError:
        logging.error('Bad set command: "%s"', message)

    ##########
    # Get
    elif mesg_type == 'get':
      try:
        await self._redis_get(client_id, json_mesg['key'])
      except ValueError:
        logging.error('Bad get command: "%s"', message)

    ##########
    # MSet
    elif mesg_type == 'mset':
      # Assume values are in key:value dict named 'values'; convert to
      # interlaced list.
      try:
        values = json_mesg['values']
        key_values = []
        for k, v in values.items():
          key_values.extend([k, v])
        await self._redis_mset(client_id, key_values)
      except ValueError:
        logging.error('Bad mset command: "%s"', message)

    ##########
    # MGet
    elif mesg_type == 'mget':
      # Assume key are in list named 'keys'
      try:
        await self._redis_mget(client_id, json_mesg['keys'])
      except ValueError:
        logging.error('Bad mget command: "%s"', message)

    ##########
    # Subscribe - accept either "channel":"name" or "channels":["name1", ...]
    elif mesg_type == 'subscribe':
      try:
        channels = json_mesg.get('channels', [json_mesg.get('channel')])
        await self._redis_subscribe(client_id, channels)
      except ValueError:
        logging.error('Bad subscribe command: "%s"', message)

    ##########
    # Unsubscribe - accept either "channel":"name" or "channels":["name1", ...]
    elif mesg_type == 'unsubscribe':
      try:
        channels = json_mesg.get('channels', [json_mesg.get('channel')])
        await self._redis_unsubscribe(client_id, channels)
      except ValueError:
        logging.error('Bad unsubscribe command: "%s"', message)

    ##########
    # PSubscribe
    elif mesg_type == 'psubscribe':
      try:
        await self._redis_psubscribe(client_id, json_mesg['channel_pattern'])
      except ValueError:
        logging.error('Bad psubscribe command: "%s"', message)

    ##########
    # Punsubscribe
    elif mesg_type == 'punsubscribe':
      try:
        await self._redis_punsubscribe(client_id, json_mesg['channel_pattern'])
      except ValueError:
        logging.error('Bad punsubscribe command: "%s"', message)

    ##########
    # Publish
    elif mesg_type == 'publish':
      try:
        await self._redis_publish(client_id,
                                  json_mesg['channel'],
                                  json_mesg['message'])
      except ValueError:
        logging.error('Bad publish command: "%s"', message)

    ##########
    # Unknown command
    else:
      logging.warning('Unknown message received from client %d: %s',
                      client_id, message)

  ############################
  async def _process_text_message(self, message, client_id):
    """Parse and process a text_message we've received from websocket."""

    # Authenticate (hah!), if needed, then pass to Redis. No,
    # authentication isn't implemented yet.

    ##########
    # Set
    if message.find('set ') == 0:
      try:
        s, key, value = message.split(sep=' ', maxsplit=2)
        await self._redis_set(client_id, key, value)
      except ValueError:
        logging.error('Bad set command: "%s"', message)

    ##########
    # Get
    elif message.find('get ') == 0:
      try:
        s, key = message.split(sep=' ')
        await self._redis_get(client_id, key)
      except ValueError:
        logging.error('Bad get command: "%s"', message)

    ##########
    # MSet
    elif message.find('mset ') == 0:
      # Assume list is sequential key value pairs, as in redis-cli
      try:
        s, *key_values = message.split(sep=' ')
        if int(len(key_values)/2) == len(key_values)/2:
          await self._redis_mset(client_id, key_values)
        else:
          logging.error('Bad mset command: must have even number of key value '
                        'elements: "%s"', message)
      except ValueError:
        logging.error('Bad mset command: "%s"', message)

    ##########
    # MGet
    elif message.find('mget ') == 0:
      try:
        s, *keys = message.split(sep=' ')
        await self._redis_mget(client_id, keys)
      except ValueError:
        logging.error('Bad mget command: "%s"', message)

    ##########
    # Subscribe
    elif message.find('subscribe ') == 0:
      try:
        sub, *channel_names = message.split(sep=' ')
        await self._redis_subscribe(client_id, channel_names)
      except ValueError:
        logging.error('Bad subscribe command: "%s"', message)

    ##########
    # Unsubscribe
    elif message.find('unsubscribe ') == 0:
      try:
        unsub, *channel_names = message.split(sep=' ')
        await self._redis_unsubscribe(client_id, channel_names)
      except ValueError:
        logging.error('Bad unsubscribe command: "%s"', message)

    ##########
    # PSubscribe
    elif message.find('psubscribe ') == 0:
      try:
        psub, channel_pattern = message.split(sep=' ')
        await self._redis_psubscribe(client_id, channel_pattern)
      except ValueError:
        logging.error('Bad psubscribe command: "%s"', message)

    ##########
    # Punsubscribe
    elif message.find('punsubscribe ') == 0:
      try:
        punsub, channel_pattern = message.split(sep=' ')
        await self._redis_punsubscribe(client_id, channel_pattern)
      except ValueError:
        logging.error('Bad punsubscribe command: "%s"', message)

    ##########
    # Publish
    elif message.find('publish ') == 0:
      try:
        pub, ch_name, send_message = message.split(sep=' ', maxsplit=2)
        await self._redis_publish(client_id, ch_name, send_message)
      except ValueError:
        logging.error('Bad publish command: "%s"', message)

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
      logging.debug('  Client %d channel %s sending websocket message %s',
                   client_id, channel_name, ws_mesg)
      await client.websocket.send(json.dumps(ws_mesg))
      logging.info('  Client %d channel %s sent websocket message %s',
                   client_id, channel_name, ws_mesg)
    logging.info('Client %d channel %s task completed', client_id, channel_name)

  ############################
  async def _redis_set(self, client_id, key, value):
    """Set a key to a value."""
    async with self.client_lock:
      client = self.client_map[client_id]
    async with client.lock:
      await client.redis.set(key, value)
    logging.info('Client %d: set %s %s', client_id, key, value)

  ############################
  async def _redis_get(self, client_id, key):
    """Get value for a key or None if it is not set."""
    async with self.client_lock:
      client = self.client_map[client_id]
    async with client.lock:
      value = await client.redis.get(key)
    if value is not None:
      value = value.decode()
    logging.info('Client %d: get %s = %s', client_id, key, value)
    ws_mesg = {
      'type': 'redis_get',
      'key': key,
      'value': value
    }
    await client.websocket.send(json.dumps(ws_mesg))

  ############################
  async def _redis_mset(self, client_id, key_value_pairs):
    """Set all key-value pairs in the passed dict."""
    async with self.client_lock:
      client = self.client_map[client_id]
    async with client.lock:
      await client.redis.mset(*key_value_pairs)
    logging.info('Client %d: mset %s', client_id, key_value_pairs)

  ############################
  async def _redis_mget(self, client_id, keys):
    """Get values for all keys; return None if a key has no value set."""
    async with self.client_lock:
      client = self.client_map[client_id]
    async with client.lock:
      values = await client.redis.mget(*keys)

    key_value_dict = {}
    for i in range(len(keys)):
      key = keys[i]
      value = values[i]
      key_value_dict[key] = value.decode() if value is not None else None

    ws_mesg = {
      'type': 'redis_mget',
      'result': key_value_dict
    }
    logging.info('Client %d: mget %s', client_id, keys)
    await client.websocket.send(json.dumps(ws_mesg))

  ############################
  async def _redis_subscribe(self, client_id, channel_names):
    """Create a reader for each channel we've subscribed to and stash the
    tasks so we can await/cancel them as appropriate when done. Do
    this iteratively, instead of as a comprehension, so we can ignore
    duplicate subscriptions.
    """
    async with self.client_lock:
      client = self.client_map[client_id]
    async with client.lock:
      for ch_name in channel_names:
        if ch_name in client.subscriptions:
          logging.info('  Client %d duplicate subscription to %s',
                       client_id, ch_name)
          continue
        ch = await client.redis.subscribe(ch_name)
        task = asyncio.ensure_future(self._channel_reader(client_id, ch[0]))
        client.subscriptions[ch_name] = task
    logging.info('Client %d: subscribe %s', client_id, channel_names)

  ############################
  async def _redis_unsubscribe(self, client_id, channel_names):
    async with self.client_lock:
      client = self.client_map[client_id]
    async with client.lock:
      # Cancel tasks for each channel we're unsubscribing from
      for ch_name in channel_names:
        task = client.subscriptions.get(ch_name, None)
        if task:
          del client.subscriptions[ch_name]
          await client.redis.unsubscribe(ch_name)
          logging.debug('  Client %d unsubscribed from %s', client_id, ch_name)
        else:
          logging.info('Client %d asking to unsubscribe from channel %s, '
                       'but no subscription found.', client_id, ch_name)
    logging.info('Client %d unsubscribe %s', client_id, channel_names)

  ############################
  async def _redis_psubscribe(self, client_id, channel_pattern):
    async with self.client_lock:
      client = self.client_map[client_id]
    async with client.lock:
      ch = await client.redis.psubscribe(channel_pattern)
      # Use psubscribe=True when creating channel reader because
      # messages it will get from Redis will be (channel, message)
      # tuples that need to be split apart.
      task = asyncio.ensure_future(self._channel_reader(client_id, ch[0],
                                                        psubscribe=True))
      client.subscriptions[channel_pattern] = task
    logging.info('Client %d psubscribe %s', client_id, channel_pattern)

  ############################
  async def _redis_punsubscribe(self, client_id, channel_pattern):
    async with self.client_lock:
      client = self.client_map[client_id]
    async with client.lock:
      ch = await client.redis.punsubscribe(channel_pattern)
    logging.info('Client %d punsubscribe %s', client_id, channel_pattern)

  ############################
  async def _redis_publish(self, client_id, ch_name, message):
    client = self.client_map[client_id]
    await client.redis.publish(ch_name, message)
    logging.info('Client %d publish %s %s', client_id, ch_name, message)

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

  parser.add_argument('--auth_token', dest='auth_token', action='store',
                      type=str, help='NOT YET IMPLEMENTED. If set, enable '
                      'access control. Allow a user providing this "master" '
                      'auth token to set auth tokens and corresponding '
                      'permissions for other users.')

  parser.add_argument('--use_json', dest='use_json', default=False,
                      action='store_true', help='If set, expect websocket '
                      'connections to send JSON-format requests.')
  parser.add_argument('--use_ssl', dest='use_ssl', default=False,
                      action='store_true', help='If set, expect websocket '
                      'clients to connect via wss://.')

  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  if args.auth_token and not args.use_json:
    logging.fatal('The --auth_token argument may only be used when '
                  '--use_json is also specified.')
    sys.exit(1)


  # Set logger format and verbosity
  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)
  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  # Create the websocket server, setting up queued senders/receivers
  server = PubSubServer(websocket=args.websocket, redis=args.redis,
                        auth_token=args.auth_token,
                        use_json=args.use_json, use_ssl=args.use_ssl)

  # Start websocket server
  try:
    server.run()
  except KeyboardInterrupt:
    logging.warning('Got interrupt')
