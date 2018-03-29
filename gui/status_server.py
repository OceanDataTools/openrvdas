#!/usr/bin/env python3
"""Run status server that reads data from Django database and feeds it
to web pages via websocket. See PROTOCOLS below for more information
about the data formats it provides.

Typically invoked via the web interface:

  # Create an expanded configuration
  logger/utils/build_config.py \
     --config test/configs/sample_cruise.json > config.json

  # If this is your first time using the test server, run
  ./manage.py makemigrations manager
  ./manage.py migrate

  # Run the Django test server
  ./manage.py runserver localhost:8000

  # In a separate window, run the script that runs servers:
  gui/run_servers.py

  # Point your browser at http://localhost:8000, log in and load the
  # configuration you created using the "Choose file" and "Load
  # configuration file" buttons at the bottom of the page.

The run_servers.py script examines the state of the Django ServerState
database to determine which servers should be running (on startup, it
sets the desired run state of both StatusServer and LoggerServer to
"run", then loops and monitors whether they are in fact running, and
restarts them if they should be and are not.

The StatusServer and LoggerServer can be run manually from the command
line as well, using the expected invocation:

  gui/logger_server.py
  gui/status_server.py

Use the --help flag to see what options are available with each.

********************************************************************* 
Note: To get this to work using the sample config sample_cruise.json
above, sample_cruise.json, you'll also need to run

  logger/utils/serial_sim.py --config test/serial_sim.py

in a separate terminal window to create the virtual serial ports the
sample config references and feed simulated data through them.)

PROTOCOLS

The StatusServer takes connections on the host:port specified on the
command line or defaults to the values WEBSOCKET_HOST and
WEBSOCKET_PORT imported from gui.settings.

It then loops, iteratively serving updates via a JSONified dictionary
whose contents depend on the requested path from that host (these are
divided out in the _serve_requests() routine, below):

/server - server status dictionary

      server_name: {'running':bool, 'desired':bool}

    Indicating whether the specified servers are running, and whether
    they're desired to be running.

/logger - serve logger statuses

      {'time_str':str,
       'status': {
          'gyr1': {<status dictionary},
          'knud': {<status dictionary},
          ...
        }
      }

/messages/<server> - serve messages emitted by the specified server

      [message, message, message,...]

    Servers at present are StatusServer and LoggerServer

/data - serve data field updates

    First waits to receive a JSONified message of the form

      [["Field1", seconds_1], ["Field2", seconds_2], ...]

    listing the fields requested and how many seconds of back-data are
    desired.

    Then sends a dictionary of back-data followed by iterative updates
    as new values for the requested fields come in:

    {"Field1": [[timestamp, val], [timestamp, val], ...],
     "Field2": [[timestamp, val], [timestamp, val], ...],
     ...
    }

"""

import argparse
import asyncio
import logging
import os
import pprint
import signal
import sys
import time
import websockets

from datetime import datetime
from json import dumps as json_dumps, loads as json_loads

sys.path.append('.')

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gui.settings')
django.setup()

from gui.models import CurrentCruise, Logger, LoggerConfigState
from gui.models import ServerMessage, StatusUpdate, ServerState

from gui.settings import WEBSOCKET_HOST, WEBSOCKET_PORT

TIME_FORMAT = '%Y-%m-%d:%H:%M:%S'

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

############################
# Translate an external signal (such as we'd get from os.kill) into a
# KeyboardInterrupt, which will signal the start() loop to exit nicely.
def kill_handler(self, signum):
  logging.warning('Received external kill')
  raise KeyboardInterrupt('Received external kill signal')

############################
# Helper to allow us to save Python logging.* messages to Django database
class WriteToDjangoHandler(logging.Handler):
  def __init__(self, logger_name):
    super().__init__()
    self.logger_name = logger_name
    self.formatter = logging.Formatter(LOGGING_FORMAT)
      
  def emit(self, record):
    message = ServerMessage(server=self.logger_name,
                            message=self.formatter.format(record))
    message.save()

############################
SERVERS = ['LoggerServer', 'StatusServer']

############################
# Helper function to retrieve latest status for each server
def get_server_status(server):
  try:
    return ServerState.objects.filter(server=server).latest('timestamp')
  except ServerState.DoesNotExist:
    return ServerState(server=server, running=False, desired=False)

################################################################################
class StatusServer:
  ############################
  def __init__(self, interval=0.5, host=WEBSOCKET_HOST, port=WEBSOCKET_PORT,
               verbosity=0):
    self.interval = interval
    self.host = host
    self.port = port
    self.status = None
    self.last_status_id = 0

    # Keep track of whether we're trying to shut down
    self.quit = False

    # Set the signal handler so that an external break will get translated
    # into a KeyboardInterrupt.
    signal.signal(signal.SIGTERM, kill_handler)

    # Set up logging levels and attach a Handler that will write log
    # messages to Django database.
    log_verbosity = LOG_LEVELS[min(verbosity, max(LOG_LEVELS))]
    logging.basicConfig(format=LOGGING_FORMAT)
    logging.getLogger().addHandler(WriteToDjangoHandler('StatusServer'))
    logging.getLogger().setLevel(log_verbosity)

  ############################
  def start(self):
    """Start grabbing status messages from Django database and feeding
    them to websocket clients."""

    logging.warning('Opening websocket server: %s:%d', self.host, self.port)
    try:
      start_server = websockets.serve(self._serve_requests, self.host,self.port)
    except OSError:
      logging.warning('Failed to open websocket %s:%s', self.host, self.port)
      self.quit = True
      return

    try:
      loop = asyncio.get_event_loop()
      loop.run_until_complete(start_server)
      loop.run_forever()
    except OSError:
      logging.warning('Failed to open websocket %s:%s', self.host, self.port)
      self.quit = True
      return

    except KeyboardInterrupt:
      logging.warning('Status server received keyboard interrupt - '
                      'trying to shut down nicely.')
      self.quit = True    # tell status-serving co-routine to stop looping

  ############################
  @asyncio.coroutine
  async def _serve_requests(self, websocket, path):

    if path == '/server':
      # Client wants server status. That's whether StatusServer (us),
      # and LoggerServer are and should be running.
      await self._serve_server_status(websocket=websocket)
    elif path == '/logger':
      # Client wants logger status - this is what we serve to the main
      # cruise page.
      await self._serve_logger_status(websocket=websocket)
    elif path.find('/messages/') == 0:
      # Client wants server_messages - path suffix may vary
      server = path[len('/messages/'):]
      await self._serve_server_messages(websocket=websocket, server=server)
    elif path == '/data':
      # Client wants logger data - this is what we serve widgets
      await self._serve_data(websocket=websocket)
    else:
      # Client wants something unknown. Complain and return
      logging.warning('Unknown status request: "%s"', path)
   
  ############################
  # If request is for server status updates (e.g. from servers.html).
  @asyncio.coroutine
  async def _serve_server_status(self, websocket, interval=0.5):
    previous_status = None

    while True:
      logging.info('_serve_server_status() looping')
      status = {}
      for server in SERVERS:
        server_status = get_server_status(server)
        status[server] = {'running':server_status.running,
                          'desired':server_status.desired}
        
      if status != previous_status:
        logging.info('sending: %s', json_dumps(status))
        try:
          await websocket.send(json_dumps(status))

        # If the client has disconnected, we're done here - go home
        except websockets.exceptions.ConnectionClosed:
          return
        previous_status = status

      await asyncio.sleep(interval)

  ############################
  # If request is for server message updates (e.g. from ???).
  @asyncio.coroutine
  async def _serve_server_messages(self, websocket, server, interval=0.5):
    latest_pk = 0

    while True:
      logging.info('_serve_server_messages(%s) looping', server)

      messages = []
      for m in ServerMessage.objects.filter(server=server, pk__gt=latest_pk):
        messages.append(m.message)
        latest_pk = max(latest_pk, m.pk)

      if messages:
        #logging.warning('%d messages for %s', len(messages), server)
        send_message = json_dumps(messages)
        try:
          await websocket.send(send_message)
        # If the client has disconnected, we're done here - go home
        except websockets.exceptions.ConnectionClosed:
          return

      await asyncio.sleep(interval)

  ############################
  # If request is for logger status updates (e.g. from index.html).
  @asyncio.coroutine
  async def _serve_logger_status(self, websocket, interval=1.0):
    previous_status = None

    while True:
      logging.info('_serve_logger_status() looping')

      # Before we do anything else, get CurrentCruise.
      try:
        cruise = CurrentCruise.objects.latest('as_of').cruise
      except (CurrentCruise.DoesNotExist, gui.models.DoesNotExist):
        logging.info('No current cruise - nothing to do.')
        await asyncio.sleep(interval)
        continue

      # Build a status dict we'll return at the end for the status
      # server (or whomever) to use.    
      status = {}
      status['cruise'] = cruise.id
      status['cruise_loaded_time'] = cruise.loaded_time.timestamp()
      if cruise.start:
        status['cruise_start'] = cruise.start.strftime(TIME_FORMAT)
      if cruise.end:
        status['cruise_end'] = cruise.end.strftime(TIME_FORMAT)

      current_mode = cruise.current_mode
      if current_mode:
        status['current_mode'] = current_mode.name

      # We'll fill in the logger statuses one at a time
      status['loggers'] = {}

      # Get config corresponding to current mode for each logger
      logger_status = {}
      for logger in Logger.objects.filter(cruise=cruise):
        logger_status = {}
      
        # What config do we want logger to be in?
        desired_config = logger.desired_config
        if desired_config:
          logger_status['desired_config'] = desired_config.name
          logger_status['desired_enabled'] = desired_config.enabled
        else:
          logger_status['desired_config'] = None
          logger_status['desired_enabled'] = True

        # What config do we think logger is actually in?
        current_config = logger.current_config
        if current_config:
          logger_status['current_config'] = current_config.name
          logger_status['current_enabled'] = current_config.enabled
          try:
            config_state = LoggerConfigState.objects.filter(
                             config=current_config).latest('pk')
            logger_status['current_errors'] = config_state.errors
          except LoggerConfigState.DoesNotExist:
            logger_status['current_errors'] = '(no config state found)'
        else:
          logger_status['current_config'] = None
          logger_status['current_enabled'] = True
          logger_status['current_errors'] = ''

        # Is the current_config the same as the config of our current mode?
        mode_match =  current_config and current_config.mode == current_mode
        logger_status['mode_match'] = mode_match
      
        # We've assembled all the information we need for status. Stash it
        status['loggers'][logger.name] = logger_status

      # Done with loggers; now add server status
      for server in SERVERS:
        server_status = get_server_status(server)
        status[server] = {'running':server_status.running,
                          'desired':server_status.desired}

      time_str = datetime.utcnow().strftime(TIME_FORMAT)
      values = { 'time_str': time_str }

      # Only send status if it's a change from previous
      if status != previous_status:
        previous_status = status
        values = {'status': status}

      # Easier to debug when using pretty-printed json dump
      #send_message = json_dumps(values, sort_keys=True, indent=2)
      send_message = json_dumps(values)
      logging.info('sending logger_status message')
      try:
        await websocket.send(send_message)

      # If the client has disconnected, we're done here - go home
      except websockets.exceptions.ConnectionClosed:
        return

      await asyncio.sleep(interval)

  ############################
  # If request is for logger data updates (e.g. from widgets).
  @asyncio.coroutine
  async def _serve_data(self, websocket, interval=0.5):
    from logger.readers.database_reader import DatabaseReader
    from database.settings import DEFAULT_DATABASE, DEFAULT_DATABASE_HOST
    from database.settings import DEFAULT_DATABASE_USER
    from database.settings import DEFAULT_DATABASE_PASSWORD

    EPSILON = 0.00001
    
    # If asking for data, we expect an initial message that is a JSON
    # list of pairs, each pair containing a field name and how many
    # seconds worth of back data we want for it.
    message = await websocket.recv()
    logging.warning('Data request: "%s"', message)
    if not message:
      logging.info('Received empty data request, doing nothing.')
      return
    try:
      field_list = json_loads(message)
    except JSONDecodeError:
      logging.warning('Received unparseable JSON request: "%s"', message)
      return

    for (field_name, num_secs) in field_list:
      logging.info('Requesting field: %s, %g secs.', field_name, num_secs)

    # Get requested back data. Note that we may have had different
    # back data time spans for different fields. Because some of these
    # might be extremely voluminous (think 30 minutes of winch data),
    # take the computational hit of initially creating a separate
    # reader for each backlog.
    fields = []
    back_data = {}
    for (field_name, num_secs) in field_list:
      fields.append(field_name)
      if not num_secs in back_data:
        back_data[num_secs] = []
      back_data[num_secs].append(field_name)

    results = {}
    now = time.time()
    for (num_secs, field_list) in back_data.items():
      # Create a DatabaseReader to get num_secs worth of back data for
      # these fields. Provide a start_time of num_secs ago, and no
      # stop_time, so we get everything up to present.
      logging.debug('Creating DatabaseReader for %s', field_list)
      logging.debug('Requesting %g seconds of timestamps from %f-%f',
                      num_secs, now-num_secs, now)
      reader = DatabaseReader(fields, DEFAULT_DATABASE, DEFAULT_DATABASE_HOST,
                              DEFAULT_DATABASE_USER, DEFAULT_DATABASE_PASSWORD)
      num_sec_results = reader.read_time_range(start_time=now-num_secs)
      logging.debug('results: %s', num_sec_results)
      results.update(num_sec_results)
                     
    # Now that we've gotten all the back results, create a single
    # DatabaseReader to read all the fields.
    reader = DatabaseReader(fields, DEFAULT_DATABASE, DEFAULT_DATABASE_HOST,
                            DEFAULT_DATABASE_USER, DEFAULT_DATABASE_PASSWORD)
    max_timestamp_seen = 0
    while True:
      # If we do have results, package them up and send them
      if results:
        send_message = json_dumps(results)
        logging.debug('Data server sending: %s', send_message)
        try:
          await websocket.send(send_message)
        except websockets.exceptions.ConnectionClosed:
          return

      # New results or not, take a nap before trying to fetch more results
      logging.debug('Sleeping %g seconds', interval)
      await asyncio.sleep(interval)

      # What's the timestamp of the most recent result we've seen?
      # Each value should be a list of (timestamp, value) pairs. Look
      # at the last timestamp in each value list.
      for field in results:
        last_timestamp = results[field][-1][0]
        max_timestamp_seen = max(max_timestamp_seen, last_timestamp)

      # Bug's corner case: if we didn't retrieve any data on the first
      # time through (because it was all too old), max_timestamp_seen
      # will be zero, causing us to retrieve *all* the data in the DB
      # on the next iteration. If we do find that max_timestamp_seen
      # is zero, set it to "now" to prevent this.
      if not max_timestamp_seen:
        max_timestamp_seen = now

      logging.debug('Results: %s', results)
      if len(results):
        logging.info('Received %d fields, max timestamp %f',
                     len(results), max_timestamp_seen)

      # Check whether there are results newer than latest timestamp
      # we've already seen.
      results = reader.read_time_range(start_time=max_timestamp_seen + EPSILON)

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
                      type=float, default=1,
                      help='How many seconds to sleep between status checks.')
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()
  
  server = StatusServer(args.interval, args.host, args.port, args.verbosity)
  server.start()
  
