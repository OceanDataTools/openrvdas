#!/usr/bin/env python3

import asyncio
import json
import logging
import queue
import ssl
import sys
import threading
import time

try:
    import websockets
    WEBSOCKETS_ENABLED = True
except ModuleNotFoundError:
    WEBSOCKETS_ENABLED = False

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402

DEFAULT_SERVER_WEBSOCKET = 'localhost:8766'


################################################################################
class CachedDataReader(Reader):
    """Subscribe to and read field values from a CachedDataServer via
    websocket connection.
    """

    def __init__(self, subscription, data_server=DEFAULT_SERVER_WEBSOCKET,
                 use_wss=False, check_cert=False):
        """
        ```
        subscription - a dictionary corresponding to the full
            fields/seconds, etc that the reader wishes, following the
            conventions described in logger/utils/cached_data_server.py
            e.g:

            subscription = {'fields':{'S330CourseTrue':{seconds:0},
                                      'S330HeadingTrue':{seconds:0}}}

        data_server - the host and port at which to try to connect to a
            CachedDataServer

        use_wss -     If True, use secure websockets

        check_cert  - If True and use_wss is True, check the server's TLS certificate
                      for validity; if a str, use as local filepath location of .pem
                      file to check against.
        ```
        When invoked in a config file, this would be:
        ```
          readers:
            class: CachedDataServer
            kwargs:
              data_server: localhost:8766
              subscription:
                fields:
                  S330CourseTrue:
                    seconds: 0
                  S330HeadingTrue:
                    seconds: 0
        ```
        """

        if not WEBSOCKETS_ENABLED:
            raise ModuleNotFoundError('CachedDataReader(): websockets module is not '
                                      'installed. Please try "pip3 install '
                                      'websockets" prior to use.')
        self.subscription = subscription
        subscription['type'] = 'subscribe'
        self.data_server = data_server
        self.use_wss = use_wss
        self.check_cert = check_cert

        # We won't initialize our websocket until the first read()
        # call. At that point we'll launch an async process in a separate
        # thread that will wait for data from the websocket and put it in
        # a queue that read() will pop from.
        self.websocket_thread = None
        self.queue = queue.Queue()
        self.quit_flag = False

    ############################
    def _parse_response(self, response):
        """Parse a CachedDataServer response and enqueue the resulting data."""
        if not response.get('type', None) == 'data':
            logging.info('Non-"data" response received from data '
                         'server: %s', response)
            return
        if not response.get('status', None) == 200:
            logging.warning('Non-"200" status received from data '
                            'server: %s', response)
            return
        data = response.get('data', None)
        if not data:
            logging.debug('No data found in data server response?: %s', response)
            return

        # If we've gotten a list, assume/hope it's a list of
        # DASRecord-like dicts; that means it's already collated for us by
        # timestamp.
        if type(data) is list:
            for entry in data:
                self.queue.put(entry)
            return

        # Otherwise we expect it to be a field dict, and need to collate
        # by timestamp manually.
        if not type(data) is dict:
            logging.warning('Data from data server not a dict?!?: %s', response)
            return

        # Collate the fields/values by timestamp
        timestamp_dict = {}
        for field, values in data.items():
            for timestamp, value in values:  # should be list of [ts, value] pairs
                if timestamp not in timestamp_dict:
                    timestamp_dict[timestamp] = {}
                timestamp_dict[timestamp][field] = value

        # Enqueue entries by timestamp
        for timestamp in sorted(timestamp_dict.keys()):
            entry = {'timestamp': timestamp, 'fields': timestamp_dict[timestamp]}
            logging.debug('Enqueuing from CDS: %s', entry)
            self.queue.put(entry)

    ############################
    def _start_websocket(self):
        """We'll run this in a separate thread as soon as we get our first
        call to read()."""

        ############################
        async def _websocket_loop(self):
            """Asynchronous inner function that will read from websocket and put
            the result in our queue.
            """
            # Iterate if we lose the websocket for some reason other than a 'quit'
            while not self.quit_flag:
                try:
                    if self.use_wss:
                        # If check_cert is a str, take it as the location of the
                        # .pem file we'll check for validity. Otherwise, if not
                        # False, take as a bool to verify by own means.
                        ws_data_server = 'wss://' + self.data_server
                        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS)
                        if self.check_cert:
                            if isinstance(self.check_cert, str):
                                ssl_context.load_verify_locations(self.check_cert)
                            else:
                                ssl_context.verify_mode = ssl.CERT_REQUIRED
                        else:
                            ssl_context.verify_mode = ssl.CERT_NONE

                    else:  # not using wss
                        ws_data_server = 'ws://' + self.data_server
                        ssl_context = None

                    logging.warning(f'CachedDataReader connecting to {ws_data_server}')
                    async with websockets.connect(ws_data_server, ssl=ssl_context) as ws:
                        logging.info(f'Connected to data server {ws_data_server}')
                        # Send our subscription request
                        await ws.send(json.dumps(self.subscription))
                        result = await ws.recv()
                        response = json.loads(result)

                        while not self.quit_flag:
                            await ws.send(json.dumps({'type': 'ready'}))
                            result = await ws.recv()
                            response = json.loads(result)
                            logging.debug('Got CachedDataServer response: %s', response)
                            self._parse_response(response)

                except BrokenPipeError:
                    pass
                except websockets.exceptions.ConnectionClosed:
                    logging.warning('CachedDataReader lost websocket connection to '
                                    'data server; trying to reconnect.')
                    await asyncio.sleep(0.2)

                except websockets.exceptions.InvalidStatusCode:
                    logging.warning('CachedDataWriter InvalidStatusCode connecting to '
                                    'data server; trying to reconnect.')
                    await asyncio.sleep(0.2)

                except OSError as e:
                    logging.info('Unable to connect to data server. '
                                 'Sleeping to try again...')
                    logging.info('Connection error: %s', str(e))
                    await asyncio.sleep(5)

        # In the outer function, get a new event loop and fire up the
        # inner, async routine.
        self.websocket_initialized = True

        # Could we also use asyncio.ensure_future(_websocket_loop(self)) ?

        websocket_event_loop = asyncio.new_event_loop()
        websocket_event_loop.run_until_complete(_websocket_loop(self))
        websocket_event_loop.close()

    ############################
    def quit(self, seconds=0):
        """Sleep N seconds, then signal quit."""
        time.sleep(seconds)
        self.quit_flag = True

    ############################
    def read(self):
        """Read/wait for data from the websocket."""

        # If we've not yet fired up the websocket thread, do that now.
        if not self.websocket_thread:
            self.websocket_thread = threading.Thread(
                name='websocket_thread',
                target=self._start_websocket,
                daemon=True)
            self.websocket_thread.start()

        # Use a timeout in our queue get() so we can periodically check if
        # we've gotten a 'quit'
        while not self.quit_flag:
            try:
                result = self.queue.get(timeout=2)
                logging.debug('Got result from queue: %s', result)
                return result
            except queue.Empty:
                logging.debug('get() timed out - trying again')
                pass

        # If we've fallen out because of a quit...
        return None
