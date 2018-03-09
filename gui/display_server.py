#!/usr/bin/env python3
"""Receive websocket requests for data fields and serve them.

Simple demonstration:

1. Make sure database is configured (using root passwor

    database/setup_mysql_connector.sh <root_pwd> <mysql_user> <user_pwd>

  e.g.

    database/setup_mysql_connector.sh rvdas rvdas rvdas

2. Start test webserver:

    ./manage.py runserver localhost:8000

3. In a separate window, start feeding the database from a sample logfile:

    logger/listener/listen.py \
        --logfile test/nmea/NBP1700/s330/raw/NBP1700_s330-2017-11-04 \
        --interval 0.5 \
        --transform_slice 1: --transform_timestamp --transform_prefix s330 \
        --transform_parse_nmea \
        --database_password rvdas --write_database rvdas@localhost:data

4. In yet a separate window, start the DisplayServer:

    gui/display_server.py -v

5. Point your browser to

    http://localhost:8000/widget/S330Pitch,S330Roll

Given any comma-separated list of fields in the url, the page will
attempt to open a websocket to the DisplayServer and will request
updates on the listed fields.


NOTE: we're going to fairly soon want to move to an implementation
where we have one process or thread doing the database queries for all
the clients at once and seeding a cache for them to read from.

"""

import argparse
import asyncio
import logging
import multiprocessing
import os
import sys
import time
import threading
import websockets

from datetime import datetime
from json import dumps as json_dumps, loads as json_loads
from json.decoder import JSONDecodeError

sys.path.append('.')

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gui.settings')
django.setup()

from logger.utils.read_json import parse_json
from logger.readers.database_reader import DatabaseFieldReader

from gui.settings import DISPLAY_HOST, DISPLAY_PORT
from database.settings import DEFAULT_DATABASE, DEFAULT_DATABASE_HOST
from database.settings import DEFAULT_DATABASE_USER, DEFAULT_DATABASE_PASSWORD

################################################################################
class DisplayServer:
  ############################
  def __init__(self, display_host=DISPLAY_HOST, display_port=DISPLAY_PORT,
               database=DEFAULT_DATABASE,
               database_host=DEFAULT_DATABASE_HOST,
               database_user=DEFAULT_DATABASE_USER,
               database_password=DEFAULT_DATABASE_PASSWORD,
               interval=0.5):

    self.interval = interval
    self.host = display_host
    self.port = display_port
    self.database = database
    self.database_host = database_host
    self.database_user = database_user
    self.database_password = database_password
    #self.runner = DjangoLoggerRunner(interval)
    
    # JSON encoding status of all the loggers, and a lock to prevent
    # anyone from messing with it while we're updating.
    self.status = None
    self.status_lock = threading.Lock()

    self.active_fields = {}
    self.active_fields_lock = threading.Lock()


    # Smallest expected increment over previously-seen timestamp
    self.epsilon = 0.00001
  
  ############################
  def start(self):
    """Note: eventually we're going to want to start the
    DatabaseFieldListener in a separate thread."""
    
    # Start the display server
    logging.warning('opening: %s:%d/display', self.host, self.port)
    start_server = websockets.serve(self._serve_display, self.host, self.port)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_server)

    try:
      loop.run_forever()      
    except KeyboardInterrupt:
      logging.warning('Display server received keyboard interrupt - '
                      'trying to shut down nicely.')

  ############################
  def register_fields(self, field_list):
    """Register that there's one more thread interested in each passed field."""
    logging.warning('FIELD_LIST: %s', field_list)
    with self.active_fields_lock:
      for field_name in field_list:
        if field_name in self.active_fields:
          self.active_fields[field_name] += 1
        else:
          self.active_fields[field_name] = 1
        logging.info('Now %d listeners for %s',
                        self.active_fields[field_name], field_name)

  ############################
  def unregister_fields(self, field_list):
    """Register that thread interested in passed fields is done."""
    with self.active_fields_lock:
      for field_name in field_list:
        if not field_name in self.active_fields:
          logging.warning('Unregistering %s, but not registered?', field_name)
        else:
          self.active_fields[field_name] -= 1
          logging.warning('Now %d listeners for %s',
                          self.active_fields[field_name], field_name)
        if not self.active_fields[field_name]:
          del self.active_fields[field_name]

  ############################
  @asyncio.coroutine
  async def _serve_display(self, websocket, path):
    # We expect the initial message to be a JSON list of pairs, each
    # pair containing a field name and how many seconds worth of back
    # data we want for it.
    message = await websocket.recv()
    logging.warning('Received message: "%s"', message)
    if not message:
      logging.info('Received empty request, doing nothing.')
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

    # Keep track of how many listeners are interested in each
    # variable. We'll want this for future optimizations where we
    # aggregate all our queries between display pages and share
    # results.
    self.register_fields(fields)

    results = {}
    now = time.time()
    for (num_secs, field_list) in back_data.items():
      # Create a DatabaseFieldReader to get num_secs worth of back
      # data for these fields. Provide a start_time of num_secs ago,
      # and no stop_time, so we get everything up to present.
      logging.warning('Creating DatabaseFileReader for %s', field_list)
      logging.warning('Requesting timestamps from %f-%f', now-num_secs, now)
      reader = DatabaseFieldReader(fields,
                                   self.database, self.database_host,
                                   self.database_user, self.database_password)
      num_sec_results = reader.read_time_range(start_time=now-num_secs)
      results.update(num_sec_results)
    max_timestamp_seen = 0
                     
    # Now that we've gotten all the back results, create a single
    # DatabaseFieldReader to read all the fields.
    reader = DatabaseFieldReader(fields,
                                 self.database, self.database_host,
                                 self.database_user, self.database_password)
    while True:
      # If we do have results, package them up and send them
      if results:
        send_message = json_dumps(results)
        logging.info('sending: %s', send_message)
        try:
          await websocket.send(send_message)

        # If the client has disconnected, we're done here - go home
        except websockets.exceptions.ConnectionClosed:
          self.unregister_fields(fields)
          return

      # New results or not, take a nap before trying to fetch more results
      logging.debug('Sleeping %g seconds', self.interval)
      await asyncio.sleep(self.interval)

      # What's the timestamp of the most recent result we've seen?
      # Each value should be a list of (timestamp, value) pairs. Look
      # at the last timestamp in each value list.
      for field in results:
        last_timestamp = results[field][-1][0]
        max_timestamp_seen = max(max_timestamp_seen, last_timestamp)
      logging.debug('Results: %s', results)
      logging.info('Received %d fields, max timestamp %f',
                   len(results), max_timestamp_seen)

      # Check whether there are results newer than latest timestamp
      # we've already seen.
      results = reader.read_time_range(start_time=max_timestamp_seen +
                                       self.epsilon)

################################################################################
if __name__ == '__main__':
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument('--display_host', dest='display_host', action='store',
                      default=DISPLAY_HOST,
                      help='Hostname for display server.')
  parser.add_argument('--display_port', dest='display_port', action='store',
                      type=int, default=DISPLAY_PORT,
                      help='Port for status server.')

  parser.add_argument('--database', dest='database', action='store',
                      default=DEFAULT_DATABASE, help='Database to read.')
  parser.add_argument('--database_host', dest='database_host', action='store',
                      default=DEFAULT_DATABASE_HOST,
                      help='Hostname for database server.')
  parser.add_argument('--database_user', dest='database_user', action='store',
                      default=DEFAULT_DATABASE_USER,
                      help='Username for database server.')
  parser.add_argument('--database_password', dest='database_password',
                       action='store', default=DEFAULT_DATABASE_PASSWORD,
                      help='User password for database server.')

  parser.add_argument('--interval', dest='interval', action='store',
                      type=float, default=1,
                      help='How many seconds to sleep between logger checks.')
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  # Set up logging levels
  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)
  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  server = DisplayServer(display_host=args.display_host,
                         display_port=args.display_port,
                         database=args.database,
                         database_host=args.database_host,
                         database_user=args.database_user,
                         database_password=args.database_password,
                         interval=args.interval)
  server.start()
  
