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

from os.path import dirname, realpath; sys.path.append(dirname(dirname(realpath(__file__))))

from server.status_server import StatusServer

TEXT_WEBSOCKET = 'localhost:8768'
TEXT_REDIS_SERVER = 'localhost:8770'

JSON_WEBSOCKET = 'localhost:8769'
JSON_REDIS_SERVER = 'localhost:8771'

################################################################################
class TestStatusServerText(unittest.TestCase):
  ###########
  # Run the Redis server as a subprocess, return proc number
  def run_redis_server(self):
    redis_port = TEXT_REDIS_SERVER.split(':')[1]
    cmd_line = ['/usr/bin/env', 'redis-server', '--port %s' % redis_port]
    self.redis_proc = subprocess.Popen(cmd_line, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)

    # If we were unable to start server, that probably means one was
    # already running on this port. Rather than trash it, bail out.
    time.sleep(0.2)
    self.assertEqual(self.redis_proc.poll(), None,
                     'Redis server already running at %s' % TEXT_REDIS_SERVER)
  
  ###########
  # Run the status server in a daemon thread - it creates a new event
  # loop for its own use.
  def run_status_server(self):
    def r_s_s_thread():
      loop = asyncio.new_event_loop()
      asyncio.set_event_loop(loop)
      server = StatusServer(websocket=TEXT_WEBSOCKET, redis=TEXT_REDIS_SERVER)
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
    async def async_test():
      async with websockets.connect('ws://' + TEXT_WEBSOCKET) as ws1:
        async with websockets.connect('ws://' + TEXT_WEBSOCKET) as ws2:

          # Test set and get
          await ws1.send('get test_k1')
          result = await ws1.recv() 
          self.assertEqual(
            result, '{"type": "redis_get", "key": "test_k1", "value": null}')
         
          await ws1.send('set test_k1 value1')
          await ws1.send('get test_k1')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_get", "key": "test_k1", "value": "value1"}')

          # Test mset and mget
          await ws1.send('mset test_k1 value1 test_k2 value2 test_k3 value3')
          await ws1.send('mget test_k1 test_k3 test_k5')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_mget", "result": {"test_k1": "value1", "test_k3": "value3", "test_k5": null}}')

          # Test subscribe, publish and unsubscribe
          await ws1.send('subscribe ch1 ch2')
          await ws2.send('publish ch3 ch3_test')
          await ws2.send('publish ch1 ch1_test')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_pub", "channel": "ch1", "message": "ch1_test"}')
          await ws1.send('unsubscribe ch1')
          await ws2.send('publish ch2 ch2_test')
          await ws2.send('publish ch1 ch1_test')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_pub", "channel": "ch2", "message": "ch2_test"}')

          # Test psubscribe, publish and punsubscribe
          await ws1.send('psubscribe pch*')
          await ws2.send('publish pch1 pch1_test')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_pub", "channel": "pch1", "message": "pch1_test"}')
          await ws2.send('publish pch3 pch3_test')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_pub", "channel": "pch3", "message": "pch3_test"}')
          await ws1.send('punsubscribe pch*')
          await ws1.send('psubscribe pch3*')
          await ws2.send('publish pch1 pch1_test')
          await ws2.send('publish pch3 pch3_test')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_pub", "channel": "pch3", "message": "pch3_test"}')

    asyncio.get_event_loop().run_until_complete(async_test())  

################################################################################
class TestStatusServerJSON(unittest.TestCase):
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
      server = StatusServer(websocket=JSON_WEBSOCKET, redis=JSON_REDIS_SERVER,
                            use_json=True)
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
    async def async_test():
      async with websockets.connect('ws://' + JSON_WEBSOCKET) as ws1:
        async with websockets.connect('ws://' + JSON_WEBSOCKET) as ws2:

          # Test set and get
          await ws1.send('{"type":"get", "key":"test_k1"}')
          result = await ws1.recv() 
          self.assertEqual(
            result, '{"type": "redis_get", "key": "test_k1", "value": null}')
         
          await ws1.send('{"type":"set", "key":"test_k1", "value": "value1"}')
          await ws1.send('{"type":"get", "key":"test_k1"}')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_get", "key": "test_k1", "value": "value1"}')

          # Test mset and mget
          await ws1.send('{"type":"mset", "values": '
                         '{"test_k1":"value1", "test_k2":"value2", "test_k3":"value3"}}')
          await ws1.send('{"type":"mget", "keys": ["test_k1", "test_k3", "test_k5"]}')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_mget", "result": '
                     '{"test_k1": "value1", "test_k3": "value3", "test_k5": null}}')

          # Test subscribe, publish and unsubscribe
          await ws1.send('{"type":"subscribe", "channels":["ch1", "ch2"]}')
          await ws2.send('{"type":"publish", "channel":"ch3", "message":"ch3_test"}')
          await ws2.send('{"type":"publish", "channel":"ch1", "message":"ch1_test"}')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_pub", "channel": "ch1", "message": "ch1_test"}')
          await ws1.send('{"type":"unsubscribe", "channels":["ch1"]}')
          await ws2.send('{"type":"publish", "channel":"ch2", "message":"ch2_test"}')
          await ws2.send('{"type":"publish", "channel":"ch1", "message":"ch1_test"}')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_pub", "channel": "ch2", "message": "ch2_test"}')

          # Test psubscribe, publish and punsubscribe
          await ws1.send('{"type":"psubscribe", "channel_pattern":"pch*"}')
          await ws2.send('{"type":"publish", "channel":"pch1", "message":"pch1_test"}')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_pub", "channel": "pch1", "message": "pch1_test"}')

          await ws2.send('{"type":"publish", "channel":"pch3", "message":"pch3_test"}')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_pub", "channel": "pch3", "message": "pch3_test"}')

          await ws1.send('{"type":"punsubscribe", "channel_pattern":"pch*"}')
          await ws1.send('{"type":"psubscribe", "channel_pattern":"pch3*"}')
          await ws2.send('{"type":"publish", "channel":"pch1", "message":"pch1_test"}')
          await ws2.send('{"type":"publish", "channel":"pch3", "message":"pch3_test"}')
          result = await ws1.recv()
          self.assertEqual(
            result, '{"type": "redis_pub", "channel": "pch3", "message": "pch3_test"}')

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
