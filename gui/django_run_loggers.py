#!/usr/bin/env python3
"""Run loggers using modes/configurations from the Django database.

Typical use:

  # Create an expanded configuration
  logger/utils/build_config.py --config test/configs/sample_cruise.json > config.json

  # If this is your first time using the test server, run
  ./manage.py makemigrations manager
  ./manage.py migrate

  # Run the Django test server
  ./manage.py runserver localhost:8000

  # Point your browser at http://localhost:8000/manager, log in and load the
  # configuration you created using the "Choose file" and "Load configuration
  # file" buttons at the bottom of the page.

  # In a separate terminal run this script to monitor the Django db and
  # run loggers as indicated.
  logger/utils/django_run_loggers_db.py -v

(To get this to work using the sample config sample_cruise.json above,
sample_cruise.json, you'll also need to run

  logger/utils/serial_sim.py --config test/serial_sim.py

in a separate terminal window to create the virtual serial ports the
sample config references and feed simulated data through them.)
"""

import argparse
import asyncio
import logging
import multiprocessing
import os
import pprint
import signal
import sys
import time
import threading
import websockets

from datetime import datetime
from json import dumps as json_dumps

sys.path.append('.')

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gui.settings')
django.setup()

from gui.models import Logger, LoggerConfig, LoggerConfigState
from gui.models import Mode, Cruise, CruiseState, CurrentCruise

from logger.utils.read_json import parse_json
from logger.listener.listen import ListenerFromLoggerConfig

from gui.settings import STATUS_HOST, STATUS_PORT

run_logging = logging.getLogger(__name__)

TIME_FORMAT = '%Y-%m-%d:%H:%M:%S'

################################################################################
class DjangoLoggerRunner:
  ############################
  def __init__(self, interval=0.5):
    """Create a LoggerRunner that reads desired states from Django DB.
    interval - number of seconds to sleep between checking/updating loggers
    """

    """
    # Do some basic checking
    has_modes = config.get('modes', None)
    if not has_modes and type(has_modes) is dict:
      raise ValueError('Improper LoggerRunner config: no "modes" dict found')
    self.configuration = config

    if mode:
      if not type(mode) is str:
        raise ValueError('LoggerRunner mode "%s" must be string' % mode)
      if not mode in has_modes:
        raise ValueError('LoggerRunner mode "%s" not in modes dict' % mode)
    self.mode = mode or config.get('default_mode', None)
    if not self.mode:
      raise ValueError('LoggerRunner no mode specified and no default found')
    """
    
    # Map logger name to config and to the process running it
    self.configs = {}
    self.processes = {}
    self.errors = {}

    # If new current cruise is loaded, we want to notice and politely
    # kill off all running loggers from the previous current cruise.
    self.current_cruise_timestamp = None
    
    self.interval = interval
    self.quit_flag = False
    
  ############################
  def check_loggers(self, halt=False):
    """Start up all the loggers using the configuration specified in
    the current mode."""

    # Build a status dict we'll return at the end for the status
    # server (or whomever) to use.    
    status = {}
    
    # Get the current cruise
    try:
      cruise = CurrentCruise.objects.latest('as_of').cruise
    except CurrentCruise.DoesNotExist:
      logging.warning('No current cruise - nothing to do.')
      return None

    # Before we do anything else, make sure that we haven't had a new
    # "current_cruise" loaded since we last looked. If we have,
    # indelicately kill off all running loggers and clear out configs.

    cruise_timestamp = cruise.loaded_time.timestamp()
    if not self.current_cruise_timestamp:
      self.current_cruise_timestamp = cruise_timestamp
    if self.current_cruise_timestamp != cruise_timestamp:
      logging.warning('New cruise loaded - killing off running loggers.')
      for logger in self.processes:
        process = self.processes[logger]
        process.terminate()
      self.processes = {}
      self.configs = {}
      self.errors = {}

      # Set our new current_cruise_timestamp
      self.current_cruise_timestamp = cruise_timestamp

      
    status['cruise'] = cruise.id
    status['cruise_loaded_time'] = cruise_timestamp
    status['cruise_start'] = cruise.start.strftime(TIME_FORMAT)
    status['cruise_end'] = cruise.end.strftime(TIME_FORMAT)

    current_mode = cruise.current_mode
    status['current_mode'] = current_mode.name

    # We'll fill in the logger statuses one at a time
    status['loggers'] = {}

    # Get config corresponding to current mode for each logger
    logger_status = {}
    for logger in Logger.objects.all():
      logger_status = {}
      
      # What config do we want logger to be in?
      desired_config = logger.desired_config
      if logger.desired_config:
        logger_status['desired_config'] = desired_config.name
        logger_status['desired_enabled'] = desired_config.enabled
      else:
        logger_status['desired_config'] = None
        logger_status['desired_enabled'] = False

      # What config is logger currently in (as far as we know)?
      current_config = self.configs.get(logger, None)
      if current_config:
        logger_status['current_config'] = current_config.name
        logger_status['current_enabled'] = current_config.enabled
        logger_status['current_error'] = self.errors.get(current_config.name, '')

      # Is the current_config the same as the config of our current mode?
      mode_match =  current_config and current_config.mode == current_mode
      logger_status['mode_match'] = mode_match
      
      # We've assembled all the information we need for status. Stash it
      status['loggers'][logger.name] = logger_status

      # Special case escape: if we've been given the 'halt' signal,
      # the desired_config of every logger is "off", represented by
      # None.
      if halt:
        desired_config = None

      # Isn't running and shouldn't be running. Nothing to do here
      if current_config is None and desired_config is None:
        continue

      # If current_config == desired_config (and is not None) and the
      # process is running, all is right with the world; skip to next.
      process = self.processes.get(logger)
      if current_config == desired_config:
        if desired_config.enabled and process and process.is_alive():
          continue

        # Two possibilities here: process is not alive, or config is
        # not enabled. If process is not alive, complain.
        if desired_config.enabled and (not process or not process.is_alive()):
          warning = 'Process for "%s" unexpectedly dead!' % logger
          run_logging.warning(warning)
          status['loggers'][logger.name]['warnings'] = warning

      # If here, process is either running and shouldn't be, or isn't
      # and should be. Kill off process if it exists.
      #
      # NOTE: not clear that terminate() cleanly shuts down a listener
      if process:
        run_logging.info('Shutting down process for %s', logger)
        process.terminate()
        self.processes[logger] = None

      # Start up a new process in the desired_config
      self.configs[logger] = desired_config
      if desired_config and desired_config.enabled:
        run_logging.info('Starting up new process for %s', logger)
        self.processes[logger] = self._start_logger(desired_config)

    # Finally, when we've looped through all the loggers, return an
    # aggregated status.
    return status
  
  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True

  ############################
  def _start_logger(self, config):
    """Create a new process running a Listener/Logger using the passed
    config, and return the Process object."""

    # Zero out any error before we try (again)
    self.errors[config.name] = None
    
    try:
      config_dict = parse_json(config.config_json)
      run_logging.debug('Starting config:\n%s', pprint.pformat(config))
      listener = ListenerFromLoggerConfig(config_dict)

      proc = multiprocessing.Process(target=listener.run)
      proc.start()
      return proc

    # If something went wrong. If it was a KeyboardInterrupt, pass it
    # along, otherwise stash error and return None
    except Exception as e:
      if e is KeyboardInterrupt:
        self.quit()
        raise e
      logging.warning('Config %s got exception: %s', config.name, str(e))
      self.errors[config.name] = str(e)

    return None

################################################################################
class LoggerServer:
  ############################
  def __init__(self, interval=0.5, host=STATUS_HOST, port=STATUS_PORT):

    self.interval = interval
    self.host = host
    self.port = port
    self.runner = DjangoLoggerRunner(interval)
    
    # JSON encoding status of all the loggers, and a lock to prevent
    # anyone from messing with it while we're updating.
    self.status = None
    self.status_lock = threading.Lock()

    # The error/warning logger we're going to use for the uh, loggers we run
    self.run_logging = logging.getLogger(__name__)

  ############################
  def start(self):
    """Start the DjangoLoggerRunner in a separate thread. It will grab
    desired configs from the Django database, try to run loggers in
    those configs, and return a status that the serve_status routine
    can pass to web pages."""
    
    logging.warning('starting run_loggers thread')
    threading.Thread(target=self._run_loggers).start()

    # Start the status server
    logging.warning('opening: %s:%d/status', self.host, self.port)
    start_server = websockets.serve(self._serve_status, self.host, self.port)

    loop = asyncio.get_event_loop()
    #loop = asyncio.new_event_loop()
    loop.run_until_complete(start_server)

    try:
      loop.run_forever()      
    except KeyboardInterrupt:
      logging.warning('Status server received keyboard interrupt - '
                      'trying to shut down nicely.')

  ############################
  def _run_loggers(self):  

    try:
      while not self.runner.quit_flag:
        logging.info('Checking loggers')
        local_status = self.runner.check_loggers()
        with self.status_lock:
          self.status =  local_status

        # Nap a little while
        time.sleep(self.interval)
    except KeyboardInterrupt:
      logging.warning('LoggerRunner received keyboard interrupt - '
                      'trying to shut down nicely.')

    # Ask the loggers to all halt
    self.status = self.runner.check_loggers(halt=True)

  ############################
  @asyncio.coroutine
  async def _serve_status(self, websocket, path):
    previous_status = None
    while True:
      time_str = datetime.utcnow().strftime(TIME_FORMAT)

      values = {
        'time_str': time_str,
      }

      # If status has changed, send new status
      with self.status_lock:
        if not self.status == previous_status:
          logging.warning('Logger status has changed')
          logging.info('New status: %s', pprint.pformat(self.status))

          # Has user reloaded the cruise configuration? If so, trigger
          # a page refresh. Otherwise, send status
          if (previous_status and
              self.status['cruise_loaded_time']
                != previous_status['cruise_loaded_time']):
              values['refresh'] = True
          else:
            values['status'] = self.status
          
          previous_status = self.status

      send_message = json_dumps(values)

      logging.info('sending: %s', send_message)
      try:
        await websocket.send(send_message)

      # If the client has disconnected, we're done here - go home
      except websockets.exceptions.ConnectionClosed:
        return

      await asyncio.sleep(self.interval)

################################################################################
if __name__ == '__main__':
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument('--host', dest='host', action='store',
                      default=STATUS_HOST,
                      help='Hostname for status server.')
  parser.add_argument('--port', dest='port', action='store', type=int,
                      default=STATUS_PORT,
                      help='Port for status server.')

  parser.add_argument('--interval', dest='interval', action='store',
                      type=float, default=1,
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

  server = LoggerServer(args.interval, args.host, args.port)
  server.start()
  
