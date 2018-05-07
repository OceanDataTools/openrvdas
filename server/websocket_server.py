#!/usr/bin/env python3

import asyncio
import json
import logging
import queue
import sys
import threading
import time
import websockets

################################################################################
class WebsocketServer:

  ############################
  def __init__(self, host, port, consumer=None, producer=None):
    """
    host, port - host and port to open as websocket

    consumer - async routine that takes a str argument and does something 
       with it. Strings retrieved from the websocket will be passed to this
       routine. If omitted, a default consumer will push the string to
       self.consumer_queue.

    producer - argument-less async routine that produces the strings we
       want to send out on the websocket. If omitted, a default consumer 
       will check self.producer_queue for for commands.
    """
    self.host = host
    self.port = port
    self.consumer = consumer or self.queued_consumer
    self.producer = producer or self.queued_producer

    self.consumer_queue = queue.Queue()
    self.producer_queue = queue.Queue()

  ############################
  # Called when we receive a message
  async def queued_consumer(self, message):
    logging.debug('Received message for queue: ' + message)
    self.consumer_queue.put(message)

  ############################
  # Called when we want something to send via the websocket
  async def queued_producer(self):
    while True:
      try:
        message = self.producer_queue.get_nowait()
        if message.strip():
          logging.info('Sending message from queue: ' + message)
          return message
      except queue.Empty:
        await asyncio.sleep(0.001)
  
  ############################
  async def _consumer_handler(self, websocket):
    try:
      async for message in websocket:
        logging.debug('WebsocketServer received message: ' + message)
        await self.consumer(message)
    except:
      logging.info('Websocket connection lost')

  ############################
  async def _producer_handler(self, websocket):
    """Here, we could either await some other producer to give us a command
    or poll."""
    # If we're waiting for an external command producer:
    try:
      while True:
        message = await self.producer()
        if message:
          await websocket.send(message)
          logging.info('WebsocketServer sent message: ' + message)
        else:
          await asyncio.sleep(1)
    except websockets.exceptions.ConnectionClosed:
      logging.info('Websocket connection lost')

  ############################
  async def _handler(self, websocket, path):
    tasks = []
    if self.consumer:
      tasks.append(asyncio.ensure_future(self._consumer_handler(websocket)))
    if self.producer:
      tasks.append(asyncio.ensure_future(self._producer_handler(websocket)))
    done, pending = await asyncio.wait(tasks,
                                       return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
      task.cancel()
    logging.info('WebsocketServer tasks completed')

  ############################
  def send(self, message):
    try:
      websocket.send(message)
      logging.info('WebsocketServer sent message: ' + message)
    except websockets.exceptions.ConnectionClosed:
      logging.info('Websocket connection lost')

  ############################
  def run(self):
    start_server = websockets.serve(self._handler, self.host, self.port)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

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
  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  try:
    host, port_str = args.websocket.split(':')
    port = int(port_str)
  except ValueError as e:
    logging.error('--websocket arg "%s" not in host:port format',args.websocket)
    exit(1)

  # If we don't pass in consumer and/or producer, WebsocketServer will
  # use its queues
  server = WebsocketServer(host=host, port=port)

  def read_commands():
    while True:
      command = input('Command? ')
      server.producer_queue.put(command)

  read_command_thread = threading.Thread(target=read_commands,
                                         name='read_commands_thread')
  read_command_thread.start()

  # Start websocket server
  server.run()
  
