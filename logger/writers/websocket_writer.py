#!/usr/bin/env python3
"""
"""
import asyncio
import logging
import ssl
import sys
import threading
import inspect

from typing import Union
from urllib.parse import urlparse

from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.writer import Writer  # noqa E402

try:
    import websockets

    WEBSOCKETS_INSTALLED = True
except ImportError:
    WEBSOCKETS_INSTALLED = False


################################################################################
class WebsocketWriter(Writer):
    ############################

    def __init__(self, uri, cert_file=None, key_file=None, quiet=False):
        """
        ```
        uri         Protocol, hostname and port to serve as. E.g. 'wss://openrvdas:8081'
                    If protocol is 'wss', use SSL, and cert_file and key_file must be specified.

        cert_file   If using ssl, the file path to relevant certificate file and key files.
        key_file
        ```
        """
        if not WEBSOCKETS_INSTALLED:
            raise ImportError('WebsocketWriter requires Python "websockets" module; '
                              'please run "pip install websockets"')
        self.uri = uri
        parsed_uri = urlparse(uri)
        self.host = parsed_uri.hostname
        self.port = parsed_uri.port
        self.protocol = parsed_uri.scheme

        # Initialize record type checking.
        super().__init__(quiet=quiet)

        if self.protocol == 'wss':
            self.ssl = True
            if (not cert_file or not key_file):
                raise ValueError('Both cert_file and key_file must be specified for wss')
        elif self.protocol == 'ws':
            self.ssl = False
            if (cert_file or key_file):
                raise ValueError('If protocol is ws, cert_file and key_file should be empty')
        else:
            raise ValueError(f'Protocol "{self.protocol}" not recognized. Must be ws or wss')

        self.cert_file = cert_file
        self.key_file = key_file

        # Map from client_id to websocket
        self.client_map = {}
        self.client_map_lock = threading.Lock()

        # Send queue for each client
        self.send_queue = {}

        # Event loop - we'll set this in run()
        self.loop = None

        # Start async websocket server in a separate thread
        self.server_run_thread = threading.Thread(target=self.run)
        self.server_run_thread.start()

    ############################
    async def _send_from_queue(self, client_id):
        """
        Asynchronously wait for stuff to show up in client's queue, pop it off
        and send to client's websocket
        """
        try:
            # The websocket, send_queue and send_queue_lock for this client
            websocket = self.client_map[client_id]
            send_queue = self.send_queue[client_id]
            while True:
                record = await send_queue.get()
                await websocket.send(record)
                logging.debug(f'WebsocketWriter sent client {client_id} record: {record}')

        except websockets.exceptions.ConnectionClosed:  # type: ignore
            logging.info(f'Websocket connection lost for client {client_id}')

    ############################
    # FIX: path=None makes this compatible with both new (1 arg) and old (2 args) libs
    async def _websocket_handler(self, websocket, path=None):
        with self.client_map_lock:
            # Find a unique client_id for this client
            client_id = 0
            while client_id in self.client_map:
                client_id += 1

            logging.info(f'New client #{client_id} attached')
            self.client_map[client_id] = websocket
            self.send_queue[client_id] = asyncio.Queue()

        # Task that produces data that we're going to send out on websocket
        tasks = [asyncio.ensure_future(self._send_from_queue(client_id))]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        # When client disconnects, delete the websocket and queue it was using
        with self.client_map_lock:
            logging.info(f'WebsocketServer client #{client_id} completed')
            del self.client_map[client_id]
            del self.send_queue[client_id]

    ############################
    def run(self):
        # Create an SSL context if we're using SSL
        ssl_context = None
        if self.ssl:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(
                certfile=self.cert_file, keyfile=self.key_file)  # type: ignore

        # Set up an event loop for the websocket server
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Build arguments dynamically to support both old and new websockets versions
        serve_kwargs = {
            'host': self.host,
            'port': self.port,
            'ssl': ssl_context
        }

        # Check signature of websockets.serve to decide on 'handler' vs 'ws_handler'
        sig = inspect.signature(websockets.serve)
        if 'handler' in sig.parameters:
            serve_kwargs['handler'] = self._websocket_handler
        else:
            serve_kwargs['ws_handler'] = self._websocket_handler

        async def runner():
            # Create the server object/context manager
            # We must do this INSIDE the coroutine so that 'websockets'
            # can find the running loop.
            server_result = websockets.serve(**serve_kwargs)

            # Modern websockets (v10+): returns an AsyncContextManager
            if hasattr(server_result, '__aenter__'):
                async with server_result:
                    # Keep the loop running while the server is active
                    await asyncio.Future()

            # Legacy websockets: returns an awaitable that yields the server
            else:
                await server_result
                # Keep the loop running
                await asyncio.Future()

        try:
            # run_until_complete starts the loop, then executes runner(),
            # which keeps running via await asyncio.Future()
            self.loop.run_until_complete(runner())
        except Exception as e:
            logging.error(f"WebsocketWriter server loop error: {e}")

    ############################
    def write(self, record: Union[str, bytes]):
        """Write a record to all connected clients"""

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            self.digest_record(record)  # inherited from BaseModule()
            return

        logging.debug(f'WebsocketWriter received record: {record}')
        with self.client_map_lock:
            for client_id, sender in self.client_map.items():
                logging.debug(f'Pushing record to client {client_id}')
                self.loop.call_soon_threadsafe(  # type: ignore
                    self.send_queue[client_id].put_nowait, record)
