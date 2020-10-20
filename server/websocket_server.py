#!/usr/bin/env python3
"""A simple websocket server. Producer and consumer routines may be
passed in that will generate messages to be sent to the websocket
(producer) and will take messages retrieved from the websocket and
process them (consumer).

The attached executable script uses default routines that look for
messages from a producer_queue to send, and add received messages to a
consumer_queue. When given a command line, the script's behavior is to
send it out to *all* attached clients. Retrieved messages are queued,
but nothing is done with them.

To run, try:

    server/websocket_server.py --websocket localhost:8765 -v

In a second window, start up a LoggerRunner as a websocket client:

    server/logger_runner.py --websocket localhost:8765 \
            --host_id client.host -v

You should see messages from the LoggerRunner appear on the
websocket_server's console, beginning with an identifying message,
then repeated status messages. If you type a command into the
websocket console, it will be relayed to the LoggerRunner, which (most
likely) will complain that it is an unrecognized command. (The only
commands the LoggerRunner recognizes over the websocket are 'quit' and
'set_configs' followed by a JSON encoding of a complete set of logger
configurations).

To explore the WebsocketServer in context, please look at the
documentation for LoggerManager, which uses a WebsocketServer to
dispatch configurations to client LoggerRunners.
"""
import asyncio
import logging
import queue
import threading
import time
import websockets


################################################################################
class WebsocketServer:
    ############################
    def __init__(self, host, port, consumer, producer,
                 on_connect=None, on_disconnect=None):
        """host, port - host and port to open as websocket

        consumer - async routine that takes a str argument and a
           client_id and does something with it. Strings retrieved from
           the websocket will be passed to this routine.

        producer - async routine that takes a client_id and produces the
           strings we want to send out to that client on the websocket.

        on_connect - optional routine to be called when a new client connects.
           Should take three parameters:
               websocket - the websocket itself, in case someone wants to store it
               client_id - an integer client id
               path - the path with which the client connected

        on_disconnect - optional routine to be called when a client
           disconnects. Should take a single integer representing client's
           unique client_id.
        """
        self.host = host
        self.port = port
        self.consumer = consumer
        self.producer = producer

        self.on_connect = on_connect
        self.on_disconnect = on_disconnect

        self.client_lock = threading.Lock()
        self.num_clients = 0
        self.client_map = {}

        self.quit_requested = False

    ############################
    async def _consumer_handler(self, websocket, client_id):
        try:
            async for message in websocket:
                logging.debug('WebsocketServer received message: ' + message)
                await self.consumer(message, client_id)

                if self.quit_requested:
                    return
        except:  # noqa E722
            logging.info('Websocket connection lost')

    ############################
    async def _producer_handler(self, websocket, client_id):
        """Here, we could either await some other producer to give us a command
        or poll."""
        # If we're waiting for an external command producer:
        try:
            while not self.quit_requested:
                message = await self.producer(client_id)
                if message:
                    await websocket.send(message)
                    logging.debug('WebsocketServer sent message: ' + message)
                else:
                    await asyncio.sleep(1)
        except websockets.exceptions.ConnectionClosed:
            logging.info('Websocket connection lost')

    ############################
    async def _handler(self, websocket, path):
        with self.client_lock:
            client_id = self.num_clients
            logging.warning('New client #%d attached', client_id)
            self.client_map[client_id] = websocket
            self.num_clients += 1
            if self.on_connect:
                self.on_connect(websocket, client_id, path)

        tasks = []

        # Task that receives data from websocket and does something with it
        if self.consumer:
            tasks.append(asyncio.ensure_future(self._consumer_handler(websocket,
                                                                      client_id)))
        # Task that produces data that we're going to send out on websocket
        if self.producer:
            tasks.append(asyncio.ensure_future(self._producer_handler(websocket,
                                                                      client_id)))
        done, pending = await asyncio.wait(tasks,
                                           return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()

        # When client disconnects, delete the queues it was using
        with self.client_lock:
            logging.info('WebsocketServer client #%d completed', client_id)
            del self.client_map[client_id]
            if self.on_disconnect:
                self.on_disconnect(client_id)

    ############################
    def clients(self):
        """Return a dict mapping client_id->websocket."""
        return self.client_map

    ############################
    def run(self):
        start_server = websockets.serve(self._handler, self.host, self.port)
        asyncio.get_event_loop().run_until_complete(start_server)
        asyncio.get_event_loop().run_forever()

    ############################
    def quit(self):
        """NOTE: This doesn't really shut things down because the event loop
        keeps running."""
        self.quit_requested = True


################################################################################
"""Below are tools for a standalone executable that takes messages
from the command line and sends them to every connected client, and
receives messages from the client websockets and prints them to the
console.

To remain non-blocking, it operates via a pair of queues:

  send_queue = {}     # client_id->queue for messages to send to ws
  receive_queue = {}  # client_id->queue for messages from ws

The websocket server is initialized with a pair of routines that use
these queues:

  queued_consumer - a consumer that takes a message and "consumes"
                    them, in this case by pushing them on the
                    receive_queue for others to process

  queued_producer - a routine that "produces" a message (by pulling
                    one off the send_queue) for the ws server to send.
"""

# Queues for our queued consumers/producers
send_queue = {}     # client_id->queue for messages to send to ws
receive_queue = {}  # client_id->queue for messages from ws

# A lock to make sure only one thread is messing with the above
# maps at any given time.
websocket_map_lock = threading.Lock()

##########################
# This is a consumer - it takes a message and does something with it


async def queued_consumer(message, client_id):
    global receive_queue
    logging.debug('Received message from client #%d: %s', client_id, message)
    receive_queue[client_id].put(message)

############################
# This is a producer - it produces a message (from the queue) to send


async def queued_producer(client_id):
    global send_queue
    while True:
        try:
            message = send_queue[client_id].get_nowait()
            if message.strip():
                logging.debug('Sending message to client #%d: %s', client_id, message)
                return message
        except queue.Empty:
            await asyncio.sleep(0.1)

############################


def register_websocket_client(websocket, client_id, path):
    """We've been alerted that a websocket client has connected.
    Register it properly."""
    global send_queue, receive_queue, websocket_map_lock
    with websocket_map_lock:
        if client_id not in send_queue:
            send_queue[client_id] = queue.Queue()
            receive_queue[client_id] = queue.Queue()
        logging.warning('Websocket client #%d has connected', client_id)

############################


def unregister_websocket_client(client_id):
    """We've been alerted that a websocket client has disconnected.
    Unegister it properly."""
    global send_queue, receive_queue, websocket_map_lock
    with websocket_map_lock:
        if client_id in send_queue:
            del send_queue[client_id]
        if client_id in receive_queue:
            del receive_queue[client_id]
        logging.warning('Websocket client #%d has disconnected', client_id)

############################


def read_commands():
    while not server.quit_requested:
        command = input('Command? ')
        for client_id, sender in send_queue.items():
            logging.warning('Pushing command to client %d: %s', client_id, command)
            send_queue[client_id].put(command)

        if command == 'quit':
            logging.warning('Quitting!')
            server.quit()

############################


def process_results():
    SHOW_LEN = 30
    while not server.quit_requested:
        with server.client_lock:
            for client_id, receiver in receive_queue.items():
                try:
                    message = receive_queue[client_id].get_nowait()
                    logging.info('#%d: %s%s', client_id, message[:SHOW_LEN],
                                 '' if len(message) < SHOW_LEN else '...')
                except queue.Empty:
                    pass
            time.sleep(0.1)


################################################################################
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--websocket', dest='websocket', action='store',
                        required=True, type=str,
                        help='Attempt to open specified host:port as websocket '
                        'and begin reading/writing data on it.')

    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    # Set logger format and verbosity
    LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)
    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    try:
        host, port_str = args.websocket.split(':')
        port = int(port_str)
    except ValueError:
        logging.error('--websocket arg "%s" not in host:port format', args.websocket)
        exit(1)

    # Create the websocket server, setting up queued senders/receivers
    server = WebsocketServer(host=host, port=port,
                             consumer=queued_consumer, producer=queued_producer,
                             on_connect=register_websocket_client,
                             on_disconnect=unregister_websocket_client)

    read_command_thread = threading.Thread(target=read_commands)
    read_command_thread.start()
    process_results_thread = threading.Thread(target=process_results)
    process_results_thread.start()

    # Start websocket server
    try:
        server.run()
    except KeyboardInterrupt:
        logging.warning('Got interrupt')

    read_command_thread.join()
    process_results_thread.join()
