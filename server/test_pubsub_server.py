#!/usr/bin/env python3

import asyncio
import json
import logging
import pprint
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

JSON_WS_PORT = '8770'
JSON_REDIS_PORT = '8771'

AUTH_WS_PORT = '8772'
AUTH_REDIS_PORT = '8773'
AUTH_TOKEN = 'a34faeracser'

################################################################################
class TestPubSubServer(unittest.TestCase):
  ###########
  @classmethod
  def setUpClass(cls):

    ########
    # Inner function we run in separate thread
    def run_pubsub_thread():
      loop = asyncio.new_event_loop()
      asyncio.set_event_loop(loop)
      server = PubSubServer(websocket='localhost:' + JSON_WS_PORT,
                            redis='localhost:' + JSON_REDIS_PORT)
      server.run()

    cmd_line = ['/usr/bin/env', 'redis-server', '--port %s' % JSON_REDIS_PORT]
    cls.redis_proc = subprocess.Popen(cmd_line, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
    time.sleep(0.2)

    # If we were unable to start server, that probably means one was
    # already running on this port. Rather than trash it, bail out.
    if cls.redis_proc.poll() is not None:
      logging.fatal('Redis server already running on port %s', JSON_REDIS_PORT)
      sys.exit(1)
    
    cls.pubsub_thread = threading.Thread(name='run_pubsub_server',
                                          target=run_pubsub_thread,
                                          daemon=True)
    cls.pubsub_thread.start()
    time.sleep(0.25)  # take a moment to let the servers get started

  ###########
  @classmethod
  def tearDownClass(cls):
    if cls.redis_proc:
      logging.info('killing redis process we started')
      cls.redis_proc.terminate()

  ###########
  async def send_and_expect(self, ws, send, expect):
    #logging.warning('SEND AND EXPECT')
    #logging.warning('Sending "%s"', send)
    await ws.send(json.dumps(send))
    #logging.warning('Expecting "%s"', expect)
    json_result = await ws.recv()
    #logging.warning('Got "%s"', json_result)
    result = json.loads(json_result)
    self.assertDictEqual(expect, result,
                         '\nexpected: %s\ngot: %s' % (expect, result))

  ###########
  async def check_stream_receives(self, ws, stream, dict_list):
    response = json.loads(await ws.recv())
    #logging.warning('response: %s', response)
    result = response.get('message')
    self.assertEqual(len(result), len(dict_list))
    for i in range(len(result)):
      self.assertEqual(len(result[i]), 3, 'received: %s' % result)
      stream_name, timestamp, message = result[i]
      self.assertEqual(stream_name, stream)
      self.assertDictEqual(message, dict_list[i])

  ############################
  def test_basic(self):
    async def async_test():
      async with websockets.connect('ws://localhost:' + JSON_WS_PORT) as ws1:
        async with websockets.connect('ws://localhost:' + JSON_WS_PORT) as ws2:


          # Test set and get
          await self.send_and_expect(ws1, {'type':'get', 'key':'test_k1'},
                                {'type': 'response', 'key': 'test_k1',
                                 'value': None,
                                 'status': 200,
                                 'request_type': 'get'})

          await self.send_and_expect(ws1, {'type':'set', 'key':'test_k1',
                                      'value': 'value1'},
                                {'type': 'response',
                                 'status': 200,
                                 'request_type': 'set'})

          await self.send_and_expect(ws1, {'type':'get', 'key':'test_k1'},
                                {'type': 'response', 'key': 'test_k1',
                                 'value': 'value1',
                                 'status': 200,
                                 'request_type': 'get'})

          # Test mset and mget
          await self.send_and_expect(ws1, {'type':'mset', 'values':
                                      {'test_k1':'value1',
                                       'test_k2':'value2',
                                       'test_k3':'value3'}},
                                {'type': 'response',
                                 'status': 200,
                                 'request_type': 'mset'})

          await self.send_and_expect(ws1, {'type':'mget',
                                      'keys': ['test_k1',
                                               'test_k3',
                                               'test_k5']},
                                {'type': 'response',
                                 'values': {'test_k1': 'value1',
                                            'test_k3': 'value3',
                                            'test_k5': None},
                                 'status': 200,
                                 'request_type': 'mget'})

    asyncio.get_event_loop().run_until_complete(async_test())

  ############################
  def test_stream_pub(self):
    async def async_test():
      async with websockets.connect('ws://localhost:' + JSON_WS_PORT) as ws1:
        async with websockets.connect('ws://localhost:' + JSON_WS_PORT) as ws2:
          # Test ssubscribe, spublish and sunsubscribe

          # Pre-load two records into stream s1
          await self.send_and_expect(ws2, {'type':'spublish', 'stream':'s1',
                                      'message':{'k1': 'value1'}},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'spublish'})
          await self.send_and_expect(ws2, {'type':'spublish', 'stream':'s1',
                                      'message':{'k1': 'value2'}},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'spublish'})
          
          await self.send_and_expect(ws1, {'type':'ssubscribe',
                                           'streams':['s1', 's2'],
                                           'start':0},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'ssubscribe'})

          await self.check_stream_receives(ws1, 's1', [{'k1': 'value1'},
                                                       {'k1': 'value2'}])

          # Unsubscribe
          await self.send_and_expect(ws1, {'type':'sunsubscribe',
                                           'streams':['s1']},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'sunsubscribe'})

          await self.send_and_expect(ws2, {'type':'spublish', 'stream':'s1',
                                      'message':{'k1': 'value4'}},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'spublish'})
          
          await self.send_and_expect(ws2, {'type':'spublish', 'stream':'s1',
                                      'message':{'k1': 'value9'}},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'spublish'})


          # When we resubscribe, we should only get new records
          await asyncio.sleep(0.1)
          await self.send_and_expect(ws1, {'type':'ssubscribe',
                                           'streams':'s1'},
                                     {'type': 'response', 'status': 200,
                                      'request_type': 'ssubscribe'})

          await self.send_and_expect(ws2, {'type':'spublish', 'stream':'s1',
                                      'message':{'k1': 'value10'}},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'spublish'})

          await self.check_stream_receives(ws1, 's1', [{'k1': 'value10'}])

          # Unsubscribe and subscribe to get all the records
          await self.send_and_expect(ws1, {'type':'sunsubscribe',
                                           'streams':'s1'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'sunsubscribe'})
          await self.send_and_expect(ws1, {'type':'ssubscribe',
                                           'streams':'s1', 'start':0},
                                     {'type': 'response', 'status': 200,
                                      'request_type': 'ssubscribe'})
          await self.check_stream_receives(ws1, 's1',
                                           [{'k1': 'value1'},
                                            {'k1': 'value2'},
                                            {'k1': 'value4'},
                                            {'k1': 'value9'},
                                            {'k1': 'value10'}])
          # Unsubscribe, wait a second, put out a record, and
          # subscribe to get all the records in last half second. We
          # should just get last one.
          await self.send_and_expect(ws1, {'type':'sunsubscribe',
                                           'streams':'s1'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'sunsubscribe'})
          await asyncio.sleep(1.0)
          await self.send_and_expect(ws2, {'type':'spublish', 'stream':'s1',
                                      'message':{'k1': 'value12'}},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'spublish'})
          await self.send_and_expect(ws1, {'type':'ssubscribe',
                                           'streams':'s1', 'start':-0.5},
                                     {'type': 'response', 'status': 200,
                                      'request_type': 'ssubscribe'})
          await self.check_stream_receives(ws1, 's1', [{'k1': 'value12'}])

    asyncio.get_event_loop().run_until_complete(async_test())

  ############################
  def test_pubsub(self):
    async def async_test():
      async with websockets.connect('ws://localhost:' + JSON_WS_PORT) as ws1:
        async with websockets.connect('ws://localhost:' + JSON_WS_PORT) as ws2:

          # Test subscribe, publish and unsubscribe
          await self.send_and_expect(ws1, {'type':'subscribe',
                                      'channels':['ch1', 'ch2']},
                                {'type': 'response',
                                 'status': 200,
                                 'request_type': 'subscribe'})

          await self.send_and_expect(ws2, {'type':'publish', 'channel':'ch3',
                                      'message':'ch3_test'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'publish'})

          await self.send_and_expect(ws2, {'type':'publish', 'channel':'ch1',
                                      'message':'ch1_test'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'publish'})
          self.assertDictEqual(json.loads(await ws1.recv()),
                               {'type': 'publish', 'channel': 'ch1',
                                'message': 'ch1_test'})


          await self.send_and_expect(ws1, {'type':'unsubscribe', 'channels':['ch1']},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'unsubscribe'})

          await self.send_and_expect(ws2, {'type':'publish', 'channel':'ch2',
                                      'message':'ch2_test'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'publish'})

          await self.send_and_expect(ws2, {'type':'publish', 'channel':'ch1',
                                      'message':'ch1_test'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'publish'})
          self.assertDictEqual(json.loads(await ws1.recv()),
                               {'type': 'publish', 'channel': 'ch2',
                                'message': 'ch2_test'})
    asyncio.get_event_loop().run_until_complete(async_test())

  ############################
  def test_psub_punsub(self):
    async def async_test():
      async with websockets.connect('ws://localhost:' + JSON_WS_PORT) as ws1:
        async with websockets.connect('ws://localhost:' + JSON_WS_PORT) as ws2:

          # Test psubscribe, publish and punsubscribe
          await self.send_and_expect(ws1, {'type':'psubscribe',
                                      'channel_pattern':'pch*'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'psubscribe'})
          await self.send_and_expect(ws2, {'type':'publish', 'channel':'pch1',
                                      'message':'pch1_test'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'publish'})
          self.assertDictEqual(json.loads(await ws1.recv()),
                               {'type': 'publish', 'channel': 'pch1',
                                'message': 'pch1_test'})

          await self.send_and_expect(ws2, {'type':'publish', 'channel':'pch3',
                                      'message':'pch3_test'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'publish'})
          self.assertEqual(json.loads(await ws1.recv()),
                           {'type': 'publish', 'channel': 'pch3',
                            'message': 'pch3_test'})

          await self.send_and_expect(ws1, {'type':'punsubscribe',
                                      'channel_pattern':'pch*'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'punsubscribe'})
          await self.send_and_expect(ws1, {'type':'psubscribe',
                                      'channel_pattern':'pch3*'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'psubscribe'})

          await self.send_and_expect(ws2, {'type':'publish', 'channel':'pch1',
                                      'message':'pch1_test'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'publish'})
          await self.send_and_expect(ws2, {'type':'publish', 'channel':'pch3',
                                      'message':'pch3_test'},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'publish'})
          self.assertDictEqual(json.loads(await ws1.recv()),
                               {'type': 'publish', 'channel': 'pch3',
                                'message': 'pch3_test'})
    asyncio.get_event_loop().run_until_complete(async_test())

  ############################
  def test_errors(self):
    async def async_test():
      async with websockets.connect('ws://localhost:' + JSON_WS_PORT) as ws1:
        async with websockets.connect('ws://localhost:' + JSON_WS_PORT) as ws2:

          # Test some errors
          await self.send_and_expect(ws1, {'missing_type':'psubscribe'},
                                {'type': 'response',
                                 'status': HTTPStatus.BAD_REQUEST,
                                 'request_type': None,
                                 'message': 'Missing request "type" field: {"missing_type": "psubscribe"}'})
          await self.send_and_expect(ws1, {'type':'unknown_type'},
                                {'type': 'response',
                                 'status': HTTPStatus.BAD_REQUEST,
                                 'request_type': 'unknown_type',
                                 'message': 'Unrecognized request type: "unknown_type"'})
          await self.send_and_expect(ws1, {'type':'set', 'key':'key1'},
                                {'type': 'response',
                                 'status': HTTPStatus.BAD_REQUEST,
                                 'request_type': 'set',
                                 'message': "set request missing key or value: {'type': 'set', 'key': 'key1'}"})

    asyncio.get_event_loop().run_until_complete(async_test())

################################################################################
class TestPubSubServerAuth(unittest.TestCase):
  ###########
  @classmethod
  def setUpClass(cls):
    logging.basicConfig(format='%(asctime)-15s %(filename)s:%(lineno)d %(message)s')

    ########
    # Inner function we run in separate thread
    def run_pubsub_thread():
      loop = asyncio.new_event_loop()
      asyncio.set_event_loop(loop)
      server = PubSubServer(websocket='localhost:' + AUTH_WS_PORT,
                            redis='localhost:' + AUTH_REDIS_PORT,
                            auth_token=AUTH_TOKEN)
      server.run()

    cmd_line = ['/usr/bin/env', 'redis-server', '--port %s ' % AUTH_REDIS_PORT]
    cls.redis_proc = subprocess.Popen(cmd_line, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
    time.sleep(0.2)

    # If we were unable to start server, that probably means one was
    # already running on this port. Rather than trash it, bail out.
    if cls.redis_proc.poll() is not None:
      logging.fatal('Redis server already running on port %s', AUTH_REDIS_PORT)
      sys.exit(1)

    
    cls.pubsub_thread = threading.Thread(name='run_pubsub_server',
                                          target=run_pubsub_thread,
                                          daemon=True)
    cls.pubsub_thread.start()
    time.sleep(0.25)  # take a moment to let the servers get started

  ###########
  @classmethod
  def tearDownClass(cls):
    if cls.redis_proc:
      logging.info('killing redis process we started')
      cls.redis_proc.terminate()

  ############################
  async def send_and_expect(self, ws, send, expect):
    await ws.send(json.dumps(send))
    result = await ws.recv()

    if not json.loads(result) == expect:
      logging.warning('result: %s', json.loads(result))
      logging.warning('expected: %s', expect)
    self.assertDictEqual(json.loads(result), expect)

  ############################
  def test_basic(self):
    async def async_test():
      async with websockets.connect('ws://localhost:' + AUTH_WS_PORT) as ws1:
        async with websockets.connect('ws://localhost:' + AUTH_WS_PORT) as ws2:

          # Test set and get
          await self.send_and_expect(ws1,
                                {"type":"get", "key":"test_k1",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'get', "key": "test_k1",
                                 "value": None})

          # Set unauthorized
          await self.send_and_expect(ws1,
                                {"type":"set", "key":"test_k1",
                                 "value": "should be unauthorized"},
                                {'type': 'response', 'status': 401,
                                 'request_type': 'set',
                                 'message': 'Unauthorized request: {"type": "set", "key": "test_k1", "value": '
                                 '"should be unauthorized"}'})
          await self.send_and_expect(ws1,
                                {"type":"get", "key":"test_k1",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'get', "key": "test_k1",
                                 "value": None})

          # Set authorized
          await self.send_and_expect(ws1,
                                {"type":"set", "key":"test_k1",
                                 "value": "value1",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'set'})

          await self.send_and_expect(ws1,
                                {"type":"get", "key":"test_k1",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'get', 'key': 'test_k1',
                                 'value': 'value1'})

          # Now create an auth for both clients: w1 can set and get,
          # and w2 can only get
          await self.send_and_expect(ws1,
                                {"type":"auth", "user":"w1",
                                 "user_auth_token":"w1_token",
                                 "auth_token": AUTH_TOKEN,
                                 "commands": ["set", "get"]},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'auth'})

          await self.send_and_expect(ws1,
                                {"type":"auth", "user":"w2",
                                 "user_auth_token":"w2_token",
                                 "auth_token": AUTH_TOKEN,
                                 "commands": ["get"]},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'auth'})

          # Now try setting without identifying ourselves as w1
          # Set unauthorized
          await self.send_and_expect(ws1,
                                {"type":"set", "key":"test_k5",
                                 "value": "should be unauthorized"},
                                {'type': 'response', 'status': 401,
                                 'request_type': 'set',
                                 'message': 'Unauthorized request: {"type": "set", "key": "test_k5", "value": "should be unauthorized"}'})

          await self.send_and_expect(ws1,
                                {"type":"get", "key":"test_k5",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'key': 'test_k5',
                                 'value': None, 'status': 200,
                                 'request_type': 'get'})

          # Now try setting, and using our w1 auth key
          # Set authorized
          await self.send_and_expect(ws1,
                                {"type":"set", "key":"test_k5",
                                 "value": "value5", "user":"w1",
                                 "auth_token": "w1_token"},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'set'})
          await self.send_and_expect(ws1,
                                {"type":"get", "key":"test_k5",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'key': 'test_k5',
                                 'value': 'value5', 'status': 200,
                                 'request_type': 'get'})

          # Now client w1 has been identified and authenticated as
          # user w1, so we should be able to set/get without passing
          # tokens.
          await self.send_and_expect(ws1,
                                {"type":"set", "key":"test_k6",
                                 "value": "value6"},
                                {'type': 'response', 'status': 200,
                                 'request_type': 'set'})
          await self.send_and_expect(ws1,
                                {"type":"get", "key":"test_k6",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'key': 'test_k6',
                                 'value': 'value6', 'status': 200,
                                 'request_type': 'get'})
          await self.send_and_expect(ws1,
                                {"type":"get", "key":"test_k6"},
                                {'type': 'response', 'key': 'test_k6',
                                 'value': 'value6', 'status': 200,
                                 'request_type': 'get'})

          # But mset should still be unauthorized.
          await self.send_and_expect(ws1,
                                {"type":"mset", "values": {"test_k7":"should be unauthorized"}},
                                {'type': 'response',
                                 'status': HTTPStatus.UNAUTHORIZED,
                                 'message': 'Unauthorized request: {"type": "mset", "values": {"test_k7": "should be unauthorized"}}',
                                 'request_type': 'mset'})
          await self.send_and_expect(ws1,
                                {"type":"get", "key":"test_k7",
                                 "auth_token": AUTH_TOKEN},
                                {'type': 'response', 'key': 'test_k7',
                                 'value': None, 'status': 200,
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
