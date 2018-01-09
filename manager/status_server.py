#!/usr/bin/env python3

import asyncio
import logging
import os
import sys
import threading
import time
import websockets

from datetime import datetime
from json import dumps as json_dumps

sys.path.append('.')

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gui.settings')
django.setup()

from manager.django_logger_runner import DjangoLoggerRunner
from manager.models import Logger, Config, Mode, Cruise
from manager.models import ConfigState, CruiseState, CurrentCruise

# Read in JSON with comments
from logger.utils.read_json import parse_json

from gui.settings import WEBSOCKET_HOST, WEBSOCKET_PORT

TIME_FORMAT = '%Y-%m-%d:%H:%M:%S'

# JSON encoding status of all the loggers, and a lock to prevent anyone from
# messing with it while we're updating.
status = None
status_lock = threading.Lock()

# The error/warning logger we're going to use for the uh, loggers we run
run_logging = logging.getLogger(__name__)

################################################################################
def run_loggers(interval):
  global status
  
  runner = DjangoLoggerRunner(interval)

  try:
    while not runner.quit_flag:
      logging.info('Checking loggers')
      local_status = runner.check_loggers()
      with status_lock:
        status =  local_status
        
      # Nap a little while
      time.sleep(interval)
  except KeyboardInterrupt:
    logging.warning('LoggerRunner received keyboard interrupt - '
                    'trying to shut down nicely.')

  # Ask the loggers to all halt
  status = runner.check_loggers(halt=True)
    
################################################################################
@asyncio.coroutine
async def serve_status(websocket, path):
  global status
  
  previous_status = None
  while True:
    time_str = datetime.utcnow().strftime(TIME_FORMAT)

    values = {
      'time_str': time_str,
    }

    # If status has changed, send new status
    with status_lock:
      if not status == previous_status:
        logging.info('Logger status has changed')
        previous_status = status
        values['status'] = status

    send_message = json_dumps(values)
    
    logging.info('sending: %s', send_message)
    await websocket.send(send_message)

    await asyncio.sleep(1)

################################################################################
if __name__ == '__main__':
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument('--host', dest='host', action='store',
                      default=WEBSOCKET_HOST,
                      help='Hostname for status server.')
  parser.add_argument('--port', dest='port', action='store', type=int,
                      default=WEBSOCKET_PORT,
                      help='Port for status server.')

  parser.add_argument('--interval', dest='interval', action='store',
                      type=int, default=1,
                      help='How many seconds to sleep between logger checks.')
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  parser.add_argument('-V', '--logger_verbosity', dest='logger_verbosity',
                      default=0, action='count',
                      help='Increase output verbosity of component loggers')
  args = parser.parse_args()

  # Set up logging levels for both ourselves and for the loggers we
  # start running
  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'

  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

  # Our verbosity
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  run_logging.setLevel(LOG_LEVELS[args.verbosity])

  # Verbosity of our component loggers (and everything else)
  args.logger_verbosity = min(args.logger_verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.logger_verbosity])

  # Start the DjangoLoggerRunner in a separate thread. It will grab
  # desired configs from the Django database, try to run loggers in
  # those configs, and return a status that the serve_status routine
  # can pass to web pages.
  logging.warning('starting run_loggers thread')
  threading.Thread(target=run_loggers, args=(args.interval,)).start()
  
  # Start the status server
  logging.warning('opening: %s:%d/status', args.host, args.port)
  start_server = websockets.serve(serve_status, args.host, args.port)

  loop = asyncio.get_event_loop()
  loop.run_until_complete(start_server)

  try:
    loop.run_forever()
  except KeyboardInterrupt:
    logging.warning('Status server received keyboard interrupt - '
                    'trying to shut down nicely.')
