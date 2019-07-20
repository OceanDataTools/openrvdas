#!/usr/bin/env python3

import asyncio
import json
import logging
import sys
import time
import unittest
import warnings
import websockets

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.readers.text_file_reader import TextFileReader
from logger.utils.cached_data_server import CachedDataServer

WEBSOCKET_PORT = 8766

class TestCachedDataServer(unittest.TestCase):

  ############################
  # To suppress resource warnings about unclosed files
  def setUp(self):
    warnings.simplefilter("ignore", ResourceWarning)

  ############################
  def test_basic(self):
    cds = CachedDataServer(port=WEBSOCKET_PORT)
    cds.cache_record({'fields':{'field_1':'value_11',
                                'field_2':'value_21',
                                'field_3':'value_31'}})

    # We call this in ensure_future, below
    async def run_test():
      async with websockets.connect('ws://localhost:%d' % WEBSOCKET_PORT) as ws:
        now = time.time()

        #####
        to_send = {'type':'fields'}
        await ws.send(json.dumps(to_send))
        result = await ws.recv()
        logging.info('got fields result: %s', result)
        response = json.loads(result)
        self.assertEqual(response.get('data', None),
                         ['field_1', 'field_2', 'field_3'])
        #####
        to_send = {'type':'publish',
                   'data':{'timestamp':time.time(),
                           'fields':{'field_1':'value_12',
                                     'field_2':'value_22'}}}
        await ws.send(json.dumps(to_send))
        result = await ws.recv()
        logging.info('got publish result: %s', result)

        #####
        to_send = {'type':'subscribe', 'interval':0.2,
                   'fields':{'field_1':{'seconds':1555507118},
                             'field_2':{'seconds':0},
                             'field_3':{'seconds':-1}}}
        await ws.send(json.dumps(to_send))
        result = await ws.recv()
        logging.info('got subscribe result: %s', result)

        #####
        to_send = {'type':'ready'}
        await ws.send(json.dumps(to_send))
        await asyncio.sleep(0.1)
        result = await ws.recv()
        logging.info('got ready 1 result: %s', result)

        response = json.loads(result)        
        self.assertEqual(len(response['data']), 2)
        self.assertEqual(len(response['data']['field_1']), 2)
        self.assertEqual(response['data']['field_1'][0][1], 'value_11')
        self.assertEqual(response['data']['field_1'][1][1], 'value_12')
        self.assertEqual(len(response['data']['field_3']), 1)
        self.assertEqual(response['data']['field_3'][0][1], 'value_31')

        #####
        to_send = {'type':'publish',
                   'data':{'timestamp':time.time(),
                           'fields':{'field_1':'value_13',
                                     'field_2':'value_23'}}}
        await ws.send(json.dumps(to_send))
        await asyncio.sleep(0.1)
        result = await ws.recv()
        logging.info('got publish result: %s', result)

        #####
        to_send = {'type':'ready'}
        await ws.send(json.dumps(to_send))
        await asyncio.sleep(0.1)
        result = await ws.recv()
        logging.info('got ready 2 result: %s', result)

        response = json.loads(result)        
        self.assertEqual(len(response['data']), 2)
        self.assertEqual(len(response['data']['field_1']), 1)
        self.assertEqual(response['data']['field_1'][0][1], 'value_13')
        self.assertEqual(len(response['data']['field_2']), 1)
        self.assertEqual(response['data']['field_2'][0][1], 'value_23')

        #####
        to_send = {'type':'publish',
                   'data':{'timestamp':time.time(),
                           'fields':{'field_3':'value_33'}}}
        await ws.send(json.dumps(to_send))
        await asyncio.sleep(0.1)
        result = await ws.recv()
        logging.info('got publish result: %s', result)

        #####
        to_send = {'type':'ready'}
        await ws.send(json.dumps(to_send))
        await asyncio.sleep(0.1)
        result = await ws.recv()
        logging.info('got ready 3 result: %s', result)

        response = json.loads(result)        
        self.assertEqual(len(response['data']), 1)
        self.assertEqual(len(response['data']['field_3']), 1)
        self.assertEqual(response['data']['field_3'][0][1], 'value_33')

    task = asyncio.ensure_future(run_test())
    time.sleep(1)
    
############################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
  unittest.main(warnings='ignore')
