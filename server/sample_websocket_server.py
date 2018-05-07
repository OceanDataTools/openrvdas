#!/usr/bin/env python3

import asyncio
import json
import sys
import threading
import time
import websockets

sys.path.append('.')
from logger.utils.read_json import read_json

# Called when we receive a status update
async def status_consumer(message):
  print('Got status: ' + message)
  
async def command_producer():
  command = input('command? ')
  print('Sending command: ' + command)
  return command

async def consumer_handler(websocket):
  async for message in websocket:
    await status_consumer(message)

async def producer_handler(websocket):
  """Here, we could either await some other producer to give us a command
  or poll."""
  """
  # If we're waiting for an external command producer:
  while True:
    message = await command_producer()
    await websocket.send(message)
    print('sent message ' + message)
  """

  await asyncio.sleep(3)
  cruise_config = read_json('test/configs/sample_cruise.json')
  await websocket.send('set_cruise %s' % json.dumps(cruise_config))

  await asyncio.sleep(3)
  await websocket.send('set_logger_config_name s330 s330->net')

  await asyncio.sleep(3)
  await websocket.send('set_mode port')

  #await asyncio.sleep(3)
  #await websocket.send('set_interval 5')

  await asyncio.sleep(3)
  await websocket.send('set_logger_config_name s330 off')

  await asyncio.sleep(3)
  await websocket.send('set_mode off')

  await asyncio.sleep(3)
  await websocket.send('quit')

async def handler(websocket, path):
  consumer_task = asyncio.ensure_future(consumer_handler(websocket))
  producer_task = asyncio.ensure_future(producer_handler(websocket))
  done, pending = await asyncio.wait([consumer_task, producer_task],
                                     return_when=asyncio.FIRST_COMPLETED)
  for task in pending:
    task.cancel()
  print('Handler tasks completed')
  await asyncio.sleep(1)

start_server = websockets.serve(handler, 'localhost', 8765)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
