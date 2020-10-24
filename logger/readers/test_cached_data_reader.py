#!/usr/bin/env python3

import logging
import sys
import threading
import unittest
import warnings

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from server.cached_data_server import CachedDataServer  # noqa: E402
from logger.readers.cached_data_reader import CachedDataReader  # noqa: E402

WEBSOCKET_PORT = 8769


class TestCachedDataReader(unittest.TestCase):

    ############################
    # To suppress resource warnings about unclosed files
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    ############################
    def test_basic(self):
        """Basic test"""
        # Create the CachedDataServer we're going to try to connect to
        # and seed it with some initial values.
        cds = CachedDataServer(port=WEBSOCKET_PORT)
        cds.cache_record({'fields': {'field_1': 'value_11',
                                     'field_2': 'value_21',
                                     'field_3': 'value_31'}})
        cds.cache_record({'fields': {'field_1': 'value_12',
                                     'field_2': 'value_22',
                                     'field_3': 'value_32'}})

        # Initialize our CachedDataReader - it won't try to connect to the
        # server until we actually call read(). We'll ask for 10 seconds
        # of back data so that we'll get both of the above records on a
        # single read and will have to parse them out.
        subscription = {'fields': {'field_1': {'seconds': 10},
                                   'field_2': {'seconds': 10},
                                   'field_3': {'seconds': 10}}}
        cdr = CachedDataReader(subscription=subscription,
                               data_server='localhost:%d' % WEBSOCKET_PORT)

        response = cdr.read()
        self.assertDictEqual(response.get('fields', None),
                             {'field_1': 'value_11',
                              'field_2': 'value_21',
                              'field_3': 'value_31'})
        response = cdr.read()
        self.assertDictEqual(response.get('fields', None),
                             {'field_1': 'value_12',
                              'field_2': 'value_22',
                              'field_3': 'value_32'})

        cds.cache_record({'fields': {'field_1': 'value_13',
                                     'field_2': 'value_23'}})
        response = cdr.read()
        self.assertDictEqual(response.get('fields', None),
                             {'field_1': 'value_13',
                              'field_2': 'value_23'})

        # Fire off a thread that will signal 'quit' in 0.5 seconds
        threading.Thread(name='quit_thread',
                         target=cdr.quit,
                         args=(0.5,)).start()

        # Read without anything coming down the pike - should hang until
        # we get 'quit'
        response = cdr.read()


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
