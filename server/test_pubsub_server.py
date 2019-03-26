#!/usr/bin/env python3

import asyncio
import json
import logging
import subprocess
import sys
import threading
import time
import unittest
import warnings
import websockets

from http import HTTPStatus

from os.path import dirname, realpath; sys.path.append(dirname(dirname(realpath(__file__))))

from server.pubsub_server import PubSubServer

JSON_WEBSOCKET = 'localhost:8770'
JSON_REDIS_SERVER = 'localhost:8771'

AUTH_WEBSOCKET = 'localhost:8772'
AUTH_REDIS_SERVER = 'localhost:8773'
AUTH_TOKEN = 'a34faeracser'

################################################################################
class TestPubSubServer(unittest.TestCase):
  ###########
  # Run the Redis server as a subprocess, return proc number
  def run_redis_server(self):
    redis_port = JSON_REDIS_SERVER.split(':')[1]
    cmd_line = ['/usr/bin/env', 'redis-server', '--port %s' % redis_port]
    self.redis_proc = subprocess.Popen(cmd_line, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)

    # If we were unable to start server, that probably means one was
    # already running on this port. Rather than trash it, bail out.
    time.sleep(0.2)

    self.assertEqual(self.redis_proc.poll(), None,
                     'Redis server already running at %s' % JSON_REDIS_SERVER)

  ###########
  # Run the status server in a daemon thread - it creates a new event
  # loop for its own use.
  def run_status_server(self):
    def r_s_s_thread():
      loop = asyncio.new_event_loop()
      asyncio.set_event_loop(loop)
      server = PubSubServer(websocket=JSON_WEBSOCKET, redis=JSON_REDIS_SERVER)
      server.run()
    self.status_thread = threading.Thread(name='run_status_server',
                                          target=r_s_s_thread, daemon=True)
    self.status_thread.start()

  ############################
  def setUp(self):
    warnings.simplefilter("ignore", ResourceWarning)

    self.run_redis_server()
    self.run_status_server()
    time.sleep(0.25)  # take a moment to let the servers get started

  ############################
  def tearDown(self):
    if self.redis_proc:
      logging.info('killing redis process we started')
      self.redis_proc.terminate()

  ############################
  def test_basic(self):
    async def send_and_expect(ws, send, expect):
      await ws.send(json.dumps(send))
      result = await ws.recv()
      self.assertDictEqual(json.loads(result), expect)

    async def async_test():
      async with websockets.connect('ws://' + JSON_WEBSOCKET) as ws1:
        async with websockets.connect('ws://' + JSON_WEBSOCKET) as ws2:

          # Test set and get
          await send_and_expect(ws1, {'type':'get', 'key':'test_k1'},
                                {'type': 'response', 'key': 'test_k1',
                                 'value': None,
                                 'status': HTTPStatus.OK,
                                 'request_type': 'get'})

          await send_and_expect(ws1, {'type':'set', 'key':'test_k1',
                                      'value': 'value1'},
                                {'type': 'response',
                                 'status': HTTPStatus.OK,
                                 'request_type': 'set'})

          await send_and_expect(ws1, {'type':'get', 'key':'test_k1'},
                                {'type': 'response', 'key': 'test_k1',
                                 'value': 'value1',
                                 'status': HTTPStatus.OK,
                                 'request_type': 'get'})

          # Test mset and mget
          await send_and_expect(ws1, {'type':'mset', 'values':
                                      {'test_k1':'value1',
                                       'test_k2':'value2',
                                       'test_k3':'value3'}},
                                {'type': 'response',
                                 'status': HTTPStatus.OK,
                                 'request_type': 'mset'})

          await send_and_expect(ws1, {'type':'mget',
                                      'keys': ['test_k1',
                                               'test_k3',
                                               'test_k5']},
                                {'type': 'response',
                                 'values': {'test_k1': 'value1',
                                            'test_k3': 'value3',
                                            'test_k5': None},
                                 'status': HTTPStatus.OK,
                                 'request_type': 'mget'})

          # Test subscribe, publish and unsubscribe
          await send_and_expect(ws1, {'type':'subscribe',
                                      'channels':['ch1', 'ch2']},
                                {'type': 'response',
                                 'status': HTTPStatus.OK,
                                 'request_type': 'subscribe'})

          await send_and_expect(ws2, {'type':'publish', 'channel':'ch3',
                                      'message':'ch3_test'},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'publish'})

          await send_and_expect(ws2, {'type':'publish', 'channel':'ch1',
                                      'message':'ch1_test'},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'publish'})
          self.assertDictEqual(json.loads(await ws1.recv()),
                               {'type': 'publish', 'channel': 'ch1',
                                'message': 'ch1_test'})


          await send_and_expect(ws1, {'type':'unsubscribe', 'channels':['ch1']},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'unsubscribe'})

          await send_and_expect(ws2, {'type':'publish', 'channel':'ch2',
                                      'message':'ch2_test'},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'publish'})

          await send_and_expect(ws2, {'type':'publish', 'channel':'ch1',
                                      'message':'ch1_test'},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'publish'})
          self.assertDictEqual(json.loads(await ws1.recv()),
                               {'type': 'publish', 'channel': 'ch2',
                                'message': 'ch2_test'})

          # Test psubscribe, publish and punsubscribe
          await send_and_expect(ws1, {'type':'psubscribe',
                                      'channel_pattern':'pch*'},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'psubscribe'})
          await send_and_expect(ws2, {'type':'publish', 'channel':'pch1',
                                      'message':'pch1_test'},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'publish'})
          self.assertDictEqual(json.loads(await ws1.recv()),
                               {'type': 'publish', 'channel': 'pch1',
                                'message': 'pch1_test'})

          await send_and_expect(ws2, {'type':'publish', 'channel':'pch3',
                                      'message':'pch3_test'},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'publish'})
          self.assertEqual(json.loads(await ws1.recv()),
                           {'type': 'publish', 'channel': 'pch3',
                            'message': 'pch3_test'})

          await send_and_expect(ws1, {'type':'punsubscribe',
                                      'channel_pattern':'pch*'},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'punsubscribe'})
          await send_and_expect(ws1, {'type':'psubscribe',
                                      'channel_pattern':'pch3*'},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'psubscribe'})

          await send_and_expect(ws2, {'type':'publish', 'channel':'pch1',
                                      'message':'pch1_test'},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'publish'})
          await send_and_expect(ws2, {'type':'publish', 'channel':'pch3',
                                      'message':'pch3_test'},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'publish'})
          self.assertDictEqual(json.loads(await ws1.recv()),
                               {'type': 'publish', 'channel': 'pch3',
                                'message': 'pch3_test'})

          # Test some errors
          await send_and_expect(ws1, {'missing_type':'psubscribe'},
                                {'type': 'response',
                                 'status': HTTPStatus.BAD_REQUEST,
                                 'request_type': None,
                                 'message': 'Missing request "type" field: {"missing_type": "psubscribe"}'})
          await send_and_expect(ws1, {'type':'unknown_type'},
                                {'type': 'response',
                                 'status': HTTPStatus.BAD_REQUEST,
                                 'request_type': 'unknown_type',
                                 'message': 'Unrecognized request type: "unknown_type"'})
          await send_and_expect(ws1, {'type':'set', 'key':'key1'},
                                {'type': 'response',
                                 'status': HTTPStatus.BAD_REQUEST,
                                 'request_type': 'set',
                                 'message': "set request missing key or value: {'type': 'set', 'key': 'key1'}"})

    asyncio.get_event_loop().run_until_complete(async_test())

################################################################################
class TestPubSubServerAuth(unittest.TestCase):
  ###########
  # Run the Redis server as a subprocess, return proc number
  def run_redis_server(self):
    redis_port = AUTH_REDIS_SERVER.split(':')[1]
    cmd_line = ['/usr/bin/env', 'redis-server', '--port %s' % redis_port]
    self.redis_proc = subprocess.Popen(cmd_line, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)

    # If we were unable to start server, that probably means one was
    # already running on this port. Rather than trash it, bail out.
    time.sleep(0.2)
    self.assertEqual(self.redis_proc.poll(), None,
                     'Redis server already running at %s' % AUTH_REDIS_SERVER)

  ###########
  # Run the status server in a daemon thread - it creates a new event
  # loop for its own use.
  def run_status_server(self):
    def r_s_s_thread():
      loop = asyncio.new_event_loop()
      asyncio.set_event_loop(loop)
      server = PubSubServer(websocket=AUTH_WEBSOCKET, redis=AUTH_REDIS_SERVER,
                            auth_token=AUTH_TOKEN)
      server.run()
    self.status_thread = threading.Thread(name='run_status_server',
                                          target=r_s_s_thread, daemon=True)
    self.status_thread.start()

  ############################
  def setUp(self):
    warnings.simplefilter("ignore", ResourceWarning)

    self.run_redis_server()
    self.run_status_server()
    time.sleep(0.25)  # take a moment to let the servers get started

  ############################
  def tearDown(self):
    if self.redis_proc:
      logging.info('killing redis process we started')
      self.redis_proc.terminate()

  ############################
  def test_basic(self):
    async def send_and_expect(ws, send, expect):
      await ws.send(json.dumps(send))
      result = await ws.recv()

      if not json.loads(result) == expect:
        logging.warning('result: %s', json.loads(result))
        logging.warning('expected: %s', expect)
      self.assertDictEqual(json.loads(result), expect)

    async def async_test():
      async with websockets.connect('ws://' + AUTH_WEBSOCKET) as ws1:
        async with websockets.connect('ws://' + AUTH_WEBSOCKET) as ws2:

          # Test set and get
          await send_and_expect(ws1,
                                {"type":"get", "key":"test_k1",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'get', "key": "test_k1",
                                 "value": None})

          # Set unauthorized
          await send_and_expect(ws1,
                                {"type":"set", "key":"test_k1",
                                 "value": "should be unauthorized"},
                                {'type': 'response', 'status': 401,
                                 'request_type': 'set',
                                 'message': 'Unauthorized request: {"type": "set", "key": "test_k1", "value": '
                                 '"should be unauthorized"}'})
          await send_and_expect(ws1,
                                {"type":"get", "key":"test_k1",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'get', "key": "test_k1",
                                 "value": None})

          # Set authorized
          await send_and_expect(ws1,
                                {"type":"set", "key":"test_k1",
                                 "value": "value1",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'set'})

          await send_and_expect(ws1,
                                {"type":"get", "key":"test_k1",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'get', 'key': 'test_k1',
                                 'value': 'value1'})

          # Now create an auth for both clients: w1 can set and get,
          # and w2 can only get
          await send_and_expect(ws1,
                                {"type":"auth", "user":"w1",
                                 "user_auth_token":"w1_token",
                                 "auth_token": AUTH_TOKEN,
                                 "commands": ["set", "get"]},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'auth'})

          await send_and_expect(ws1,
                                {"type":"auth", "user":"w2",
                                 "user_auth_token":"w2_token",
                                 "auth_token": AUTH_TOKEN,
                                 "commands": ["get"]},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'auth'})

          # Now try setting without identifying ourselves as w1
          # Set unauthorized
          await send_and_expect(ws1,
                                {"type":"set", "key":"test_k5",
                                 "value": "should be unauthorized"},
                                {'type': 'response', 'status': 401,
                                 'request_type': 'set',
                                 'message': 'Unauthorized request: {"type": "set", "key": "test_k5", "value": "should be unauthorized"}'})

          await send_and_expect(ws1,
                                {"type":"get", "key":"test_k5",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'key': 'test_k5',
                                 'value': None, 'status': HTTPStatus.OK,
                                 'request_type': 'get'})

          # Now try setting, and using our w1 auth key
          # Set authorized
          await send_and_expect(ws1,
                                {"type":"set", "key":"test_k5",
                                 "value": "value5", "user":"w1",
                                 "auth_token": "w1_token"},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'set'})
          await send_and_expect(ws1,
                                {"type":"get", "key":"test_k5",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'key': 'test_k5',
                                 'value': 'value5', 'status': HTTPStatus.OK,
                                 'request_type': 'get'})

          # Now client w1 has been identified and authenticated as
          # user w1, so we should be able to set/get without passing
          # tokens.
          await send_and_expect(ws1,
                                {"type":"set", "key":"test_k6",
                                 "value": "value6"},
                                {'type': 'response', 'status': HTTPStatus.OK,
                                 'request_type': 'set'})
          await send_and_expect(ws1,
                                {"type":"get", "key":"test_k6",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'key': 'test_k6',
                                 'value': 'value6', 'status': HTTPStatus.OK,
                                 'request_type': 'get'})
          await send_and_expect(ws1,
                                {"type":"get", "key":"test_k6"},
                                {'type': 'response', 'key': 'test_k6',
                                 'value': 'value6', 'status': HTTPStatus.OK,
                                 'request_type': 'get'})

          # But mset should still be unauthorized.
          await send_and_expect(ws1,
                                {"type":"mset", "values": {"test_k7":"should be unauthorized"}},
                                {'type': 'response',
                                 'status': HTTPStatus.UNAUTHORIZED,
                                 'message': 'Unauthorized request: {"type": "mset", "values": {"test_k7": "should be unauthorized"}}',
                                 'request_type': 'mset'})
          await send_and_expect(ws1,
                                {"type":"get", "key":"test_k7",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'key': 'test_k7',
                                 'value': None, 'status': HTTPStatus.OK,
                                 'request_type': 'get'})

    asyncio.get_event_loop().run_until_complete(async_test())

################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  logging.basicConfig(format=LOGGING_FORMAT)
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  #logging.getLogger().setLevel(logging.DEBUG)
  unittest.main(warnings='ignore')
