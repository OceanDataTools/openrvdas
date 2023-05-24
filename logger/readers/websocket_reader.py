#!/usr/bin/env python3

import asyncio
import logging
import queue
import ssl
import threading
import time
import websockets

DEFAULT_SERVER_WEBSOCKET = 'localhost:8766'


################################################################################
class WebsocketReader():
    """Connect to a websocket served by a WebsocketWriter, and service read()
    requests from it.
    """

    def __init__(self, uri, check_cert=False):
        """
        ```
        uri -      Hostname, port and protocol, (e.g. wss://localhost:8080) at which
                   to try to connect to a WebsocketWriter

        check_cert  - If True, and uri protocol is 'wss', check the server's TLS certificate
                      for validity; if a str, use as local filepath location of .pem
                      file to check against.
        ```
        """
        self.uri = uri
        self.check_cert = check_cert

        # We won't initialize our websocket until the first read()
        # call. At that point we'll launch an async process in a separate
        # thread that will wait for data from the websocket and put it in
        # a queue that read() will pop from.
        self.websocket_thread = None
        self.queue = queue.Queue()
        self.quit_flag = False

    ############################
    def _start_websocket(self):
        """We'll run this in a separate thread as soon as we get our first
        call to read()."""

        ############################
        async def _websocket_loop(self):
            """Asynchronous inner function that will connect to websocket,
            iteratively try to read from it and put the result in our queue.
            """
            # Iterate if we lose the websocket for some reason other than a 'quit'
            while not self.quit_flag:
                try:
                    if self.uri.find('wss://') == 0:  # using wss
                        # If check_cert is a str, take it as the location of the
                        # .pem file we'll check for validity. Otherwise, if not
                        # False, take as a bool to verify by own means.
                        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                        if self.check_cert:
                            if isinstance(self.check_cert, str):
                                ssl_context.load_verify_locations(self.check_cert)
                            else:
                                ssl_context.verify_mode = ssl.CERT_REQUIRED
                        else:
                            ssl_context.check_hostname = False
                            ssl_context.verify_mode = ssl.CERT_NONE

                    else:  # not using wss
                        ssl_context = None

                    logging.debug(f'WebsocketReader connecting to {self.uri}')
                    async with websockets.connect(self.uri, ssl=ssl_context) as ws: # type: ignore
                        logging.info(f'Connected to WebsocketWriter at {self.uri}')

                        while not self.quit_flag:
                            record = await ws.recv()
                            logging.debug(f'WebsocketReader got record {record}')
                            self.queue.put(record)

                except BrokenPipeError:
                    logging.info(f'WebsocketReader BrokenPipeError connecting to {self.uri}')
                    pass
                except AttributeError as e:
                    logging.warning(f'WebsocketReader websocket loop error: {e}')
                except websockets.exceptions.ConnectionClosed: # type: ignore
                    logging.info('WebsocketReader lost websocket connection to '
                                 'data server; trying to reconnect.')
                    await asyncio.sleep(0.2)
                except websockets.exceptions.InvalidStatusCode: # type: ignore
                    logging.info('WebsocketReader InvalidStatusCode connecting to '
                                 'data server; trying to reconnect.')
                    await asyncio.sleep(0.2)
                except OSError as e:
                    logging.info('Unable to connect to websocket. Sleeping to try again...')
                    logging.info(f'Connection error: {e}')
                    await asyncio.sleep(2)

        # In the outer function, get a new event loop and fire up the
        # inner, async routine.
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
                result = self.queue.get(block=True, timeout=2)
                logging.debug('Got result from queue: %s', result)
                return result
            except queue.Empty:
                logging.debug('get() timed out - trying again')
                pass

        # If we've fallen out because of a quit...
        return None
