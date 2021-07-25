#!/usr/bin/env python3

from server.cached_data_server import CachedDataServer
from os import environ
import asyncio
import json
import logging
import sys
import tempfile
import time
import unittest
import warnings
import websockets

from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))

# Django 3 doesn't play nicely when mixing sync and async, so when we
# try to run the Django 'manage.py test' command, it gets unhappy
# unless we explicitly tell it to chill.
environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


class TestCachedDataServer(unittest.TestCase):

    ############################
    # To suppress resource warnings about unclosed files
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    ############################
    def test_basic(self):
        WEBSOCKET_PORT = 8767
        cds = CachedDataServer(port=WEBSOCKET_PORT)
        cds.cache_record({'fields': {'basic_field_1': 'value_11',
                                     'basic_field_2': 'value_21',
                                     'basic_field_3': 'value_31'}})

        # We call this in ensure_future, below
        async def run_test():
            async with websockets.connect('ws://localhost:%d' % WEBSOCKET_PORT) as ws:
                #####
                to_send = {'type': 'fields'}
                await ws.send(json.dumps(to_send))
                result = await ws.recv()
                logging.info('got fields result: %s', result)
                response = json.loads(result)
                self.assertEqual(response.get('data', None),
                                 ['basic_field_1', 'basic_field_2', 'basic_field_3'])
                #####
                to_send = {'type': 'publish',
                           'data': {'timestamp': time.time(),
                                    'fields': {'basic_field_1': 'value_12',
                                               'basic_field_2': 'value_22'}}}
                await ws.send(json.dumps(to_send))
                result = await ws.recv()
                logging.info('got publish result: %s', result)

                #####
                to_send = {'type': 'subscribe', 'interval': 0.2,
                           'fields': {'basic_field_1': {'seconds': 1555507118},
                                      'basic_field_2': {'seconds': 0},
                                      'basic_field_3': {'seconds': -1}}}
                await ws.send(json.dumps(to_send))
                result = await ws.recv()
                logging.info('got subscribe result: %s', result)

                #####
                to_send = {'type': 'ready'}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got ready 1 result: %s', result)

                response = json.loads(result)
                self.assertEqual(len(response['data']), 2)
                self.assertEqual(len(response['data']['basic_field_1']), 2)
                self.assertEqual(response['data']['basic_field_1'][0][1], 'value_11')
                self.assertEqual(response['data']['basic_field_1'][1][1], 'value_12')
                self.assertEqual(len(response['data']['basic_field_3']), 1)
                self.assertEqual(response['data']['basic_field_3'][0][1], 'value_31')

                #####
                to_send = {'type': 'publish',
                           'data': {'timestamp': time.time(),
                                    'fields': {'basic_field_1': 'value_13',
                                               'basic_field_2': 'value_23'}}}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got publish result: %s', result)

                #####
                to_send = {'type': 'ready'}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got ready 2 result: %s', result)

                response = json.loads(result)
                self.assertEqual(len(response['data']), 2)
                self.assertEqual(len(response['data']['basic_field_1']), 1)
                self.assertEqual(response['data']['basic_field_1'][0][1], 'value_13')
                self.assertEqual(len(response['data']['basic_field_2']), 1)
                self.assertEqual(response['data']['basic_field_2'][0][1], 'value_23')

                #####
                to_send = {'type': 'publish',
                           'data': {'timestamp': time.time(),
                                    'fields': {'basic_field_3': 'value_33'}}}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got publish result: %s', result)

                #####
                to_send = {'type': 'ready'}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got ready 3 result: %s', result)

                response = json.loads(result)
                self.assertEqual(len(response['data']), 1)
                self.assertEqual(len(response['data']['basic_field_3']), 1)
                self.assertEqual(response['data']['basic_field_3'][0][1], 'value_33')

        asyncio.new_event_loop().run_until_complete(run_test())
        time.sleep(1)

    ############################
    def test_wildcard(self):
        WEBSOCKET_PORT = 8768
        cds = CachedDataServer(port=WEBSOCKET_PORT)
        cds.cache_record({'fields': {'wild_field_1': 'value_11',
                                     'wild_field_2': 'value_21',
                                     'wild_field_3': 'value_31',
                                     'wild_field_4': 'value_11',
                                     'wild_field_51': 'value_21',
                                     'wild_field_61': 'value_31'}})

        # We call this in ensure_future, below
        async def run_test():
            async with websockets.connect('ws://localhost:%d' % WEBSOCKET_PORT) as ws:
                #####
                to_send = {'type': 'fields'}
                await ws.send(json.dumps(to_send))
                result = await ws.recv()
                logging.info('got fields result: %s', result)
                response = json.loads(result)
                self.assertEqual(response.get('data', None),
                                 ['wild_field_1', 'wild_field_2', 'wild_field_3',
                                  'wild_field_4', 'wild_field_51', 'wild_field_61'])
                #####
                to_send = {'type': 'publish',
                           'data': {'timestamp': time.time(),
                                    'fields': {'wild_field_1': 'value_12',
                                               'wild_field_2': 'value_22'}}}
                await ws.send(json.dumps(to_send))
                result = await ws.recv()
                logging.info('got publish result: %s', result)

                #####
                to_send = {'type': 'subscribe', 'interval': 0.2,
                           'fields': {'wild_field_*': {'seconds': 1555507118}}}
                await ws.send(json.dumps(to_send))
                result = await ws.recv()
                logging.info('got subscribe result: %s', result)

                #####
                to_send = {'type': 'ready'}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got ready 1 result: %s', result)

                response = json.loads(result)
                self.assertEqual(len(response['data']), 6)
                self.assertEqual(len(response['data']['wild_field_1']), 2)
                self.assertEqual(response['data']['wild_field_1'][0][1], 'value_11')
                self.assertEqual(response['data']['wild_field_1'][1][1], 'value_12')
                self.assertEqual(len(response['data']['wild_field_3']), 1)
                self.assertEqual(response['data']['wild_field_3'][0][1], 'value_31')

                #####
                to_send = {'type': 'publish',
                           'data': {'timestamp': time.time(),
                                    'fields': {'wild_field_1': 'value_13',
                                               'wild_field_2': 'value_23'}}}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got publish result: %s', result)

                #####
                to_send = {'type': 'ready'}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got ready 2 result: %s', result)

                response = json.loads(result)
                self.assertEqual(len(response['data']), 2)
                self.assertEqual(len(response['data']['wild_field_1']), 1)
                self.assertEqual(response['data']['wild_field_1'][0][1], 'value_13')
                self.assertEqual(len(response['data']['wild_field_2']), 1)
                self.assertEqual(response['data']['wild_field_2'][0][1], 'value_23')

                #####
                to_send = {'type': 'publish',
                           'data': {'timestamp': time.time(),
                                    'fields': {'wild_field_3': 'value_33'}}}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got publish result: %s', result)

                #####
                to_send = {'type': 'ready'}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got ready 3 result: %s', result)

                response = json.loads(result)
                self.assertEqual(len(response['data']), 1)
                self.assertEqual(len(response['data']['wild_field_3']), 1)
                self.assertEqual(response['data']['wild_field_3'][0][1], 'value_33')

        asyncio.new_event_loop().run_until_complete(run_test())
        time.sleep(1)

    ############################
    def test_disk_cache(self):
        WEBSOCKET_PORT = 8770
        tmpdir = tempfile.TemporaryDirectory()
        disk_cache = tmpdir.name + '/disk_cache'
        cds = CachedDataServer(port=WEBSOCKET_PORT, disk_cache=disk_cache)
        cds.cache_record({'fields': {'field_1': 'value_11a',
                                     'field_2': 'value_21a',
                                     'field_3': 'value_31a'}})

        # We call this in ensure_future, below
        async def run_test():
            async with websockets.connect('ws://localhost:%d' % WEBSOCKET_PORT) as ws:
                #####
                to_send = {'type': 'fields'}
                await ws.send(json.dumps(to_send))
                result = await ws.recv()
                logging.info('got fields result: %s', result)
                response = json.loads(result)
                self.assertEqual(response.get('data', None),
                                 ['field_1', 'field_2', 'field_3'])
                #####
                to_send = {'type': 'publish',
                           'data': {'timestamp': time.time(),
                                    'fields': {'field_1': 'value_12a',
                                               'field_2': 'value_22a'}}}
                await ws.send(json.dumps(to_send))
                result = await ws.recv()
                logging.info('got publish result: %s', result)

                #####
                to_send = {'type': 'subscribe', 'interval': 0.2,
                           'fields': {'field_1': {'seconds': 1555507118},
                                      'field_2': {'seconds': 0},
                                      'field_3': {'seconds': -1}}}
                await ws.send(json.dumps(to_send))
                result = await ws.recv()
                logging.info('got subscribe result: %s', result)

                #####
                to_send = {'type': 'ready'}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got ready 1 result: %s', result)

                response = json.loads(result)
                self.assertEqual(len(response['data']), 2)
                self.assertEqual(len(response['data']['field_1']), 2)
                self.assertEqual(response['data']['field_1'][0][1], 'value_11a')
                self.assertEqual(response['data']['field_1'][1][1], 'value_12a')
                self.assertEqual(len(response['data']['field_3']), 1)
                self.assertEqual(response['data']['field_3'][0][1], 'value_31a')

                #####
                to_send = {'type': 'publish',
                           'data': {'timestamp': time.time(),
                                    'fields': {'field_1': 'value_13a',
                                               'field_2': 'value_23a'}}}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got publish result: %s', result)

                #####
                to_send = {'type': 'ready'}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got ready 2 result: %s', result)

                response = json.loads(result)
                self.assertEqual(len(response['data']), 2)
                self.assertEqual(len(response['data']['field_1']), 1)
                self.assertEqual(response['data']['field_1'][0][1], 'value_13a')
                self.assertEqual(len(response['data']['field_2']), 1)
                self.assertEqual(response['data']['field_2'][0][1], 'value_23a')

                #####
                to_send = {'type': 'publish',
                           'data': {'timestamp': time.time(),
                                    'fields': {'field_3': 'value_33a'}}}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got publish result: %s', result)

                #####
                to_send = {'type': 'ready'}
                await ws.send(json.dumps(to_send))
                await asyncio.sleep(0.1)
                result = await ws.recv()
                logging.info('got ready 3 result: %s', result)

                response = json.loads(result)
                self.assertEqual(len(response['data']), 1)
                self.assertEqual(len(response['data']['field_3']), 1)
                self.assertEqual(response['data']['field_3'][0][1], 'value_33a')

        asyncio.new_event_loop().run_until_complete(run_test())
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

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
    unittest.main(warnings='ignore')
