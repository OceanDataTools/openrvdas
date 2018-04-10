#!/usr/bin/env python3
"""Run loggers using modes/configurations from the Django database.

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

"""

import argparse
import logging
import multiprocessing
import os
import pprint
import signal
import sys
import time

from json import dumps as json_dumps

sys.path.append('.')

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gui.settings')
django.setup()

from gui.models import Logger, LoggerConfigState
from gui.models import Cruise, CurrentCruise
from gui.models import ServerMessage, StatusUpdate

from logger.utils.read_json import parse_json
from logger.listener.listen import ListenerFromLoggerConfig

run_logging = logging.getLogger(__name__)

TIME_FORMAT = '%Y-%m-%d:%H:%M:%S'

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

# Number of times we'll try a failing logger before giving up
DEFAULT_NUM_TRIES = 3

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
  
################################################################################
class LoggerServer:
  ############################
  def __init__(self, interval=0.5, num_tries=3,
               verbosity=0, logger_verbosity=0):
    """Read desired/current logger configs from Django DB and try to run the
    loggers specified in those configs.

    interval - number of seconds to sleep between checking/updating loggers

    num_tries - number of times to try a failed server before giving up
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

    # Set the signal handler so that an external break will get translated
    # into a KeyboardInterrupt.
    signal.signal(signal.SIGTERM, kill_handler)

    # Set up logging levels for both ourselves and for the loggers we
    # start running. Attach a Handler that will write log messages to
    # Django database.
    logging.basicConfig(format=LOGGING_FORMAT)
    #run_logging.basicConfig(format=LOGGING_FORMAT)

    log_verbosity = LOG_LEVELS[min(verbosity, max(LOG_LEVELS))]
    log_logger_verbosity = LOG_LEVELS[min(logger_verbosity, max(LOG_LEVELS))]
    
    run_logging.addHandler(WriteToDjangoHandler('LoggerServer'))
    logging.getLogger().addHandler(WriteToDjangoHandler('LoggerServer'))

    run_logging.setLevel(log_verbosity)
    logging.getLogger().setLevel(log_logger_verbosity)
    
  ############################
  def start(self):
    """Loop, checking that loggers are in the state they should be,
    getting them into that state if they aren't, and saving the resulting
    status to a StatusUpdate record in the database."""

    try:
      while not self.quit_flag:
        logging.info('Checking loggers')
        status = self.check_loggers()
        if status:
          StatusUpdate(server='LoggerServer',
                       cruise=status.get('cruise', None),
                       status=json_dumps(status)).save()
        time.sleep(self.interval)

    except KeyboardInterrupt:
      logging.warning('LoggerServer received keyboard interrupt - '
                      'trying to shut down nicely.')

    # Ask the loggers to all halt, and stop looping
    self.status = self.check_loggers(halt=True)
    self.quit()
  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True

  ############################
  def check_loggers(self, halt=False):
    """Check the desired state of all loggers and start/stop them accordingly.
    """

    # We'll fill in the logger statuses one at a time
    loggers = {}
    for logger in Logger.objects.all():
      warnings = []
      logger_status = {}
      # What config do we want logger to be in?
      desired_config = logger.desired_config
      # What config is logger currently in (as far as we know)?
      current_config = self.configs.get(logger, None)

      # Regardless of what the database says, is logger running?
      logger_process = self.processes.get(logger, None)
      logger_running = bool(logger_process and logger_process.is_alive())

      # If not, and if it should be, complain
      if current_config and current_config.enabled and not logger_running:
        warning = 'Process for "%s" unexpectedly dead!' % logger
        run_logging.warning(warning)
        warnings.append(warning)
        LoggerConfigState(config=current_config, desired=True,
                          running=False, errors=warning).save()

      # Special case: if we've been given the 'halt' signal, the
      # desired_config of every logger is "off", represented by None.
      if halt:
        desired_config = None

      # If we don't think our current config should be running
      if (desired_config is None or not desired_config.enabled or
          desired_config != current_config):
        if logger_running:
          run_logging.info('Shutting down process for %s', logger)
          self.processes[logger].terminate()
          self.processes[logger] = None

        # Record that we've shut current config down
        if current_config:
          LoggerConfigState(config=current_config, running=False).save()

      # If we need to change current_config to the desired_config
      if desired_config != current_config:
        self.configs[logger] = desired_config
        logger.current_config = desired_config
        logger.save()

        # Record that we've shut current config down
        if desired_config:
          LoggerConfigState(config=desired_config, desired=True,
                            running=desired_config.enabled).save()

      # Is our new current_config enabled? If so, run its logger
      if desired_config and desired_config.enabled:
        logger_process = self.processes.get(logger, None)
        logger_running = bool(logger_process and logger_process.is_alive())
        if not logger_running:
          run_logging.info('Starting up new process for %s', logger)
          self.processes[logger] = self._start_logger(desired_config)

      # We've assembled all the information we need for status. Stash it
      if desired_config:
        logger_status = {
          'desired_config': desired_config.name,
          'desired_enabled': desired_config.enabled,
          'current_config': desired_config.name,
          'current_enabled': desired_config.enabled,
          'current_error': self.errors.get(desired_config.name,''),
          'warnings': warnings
        }
      else:
        logger_status = {
          'desired_config': None,
          'desired_enabled': False,
          'current_config': None,
          'current_enabled': False
        }
      loggers[logger.name] = logger_status

    # Build a status dict we'll return at the end for the status
    # server (or whomever) to use.
    status = {
      'loggers': loggers,
    }
    return status
  
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
      LoggerConfigState(config=config, desired=True,
                        running=False, errors=str(e)).save()

    return None

################################################################################
if __name__ == '__main__':
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument('--interval', dest='interval', action='store',
                      type=float, default=1,
                      help='How many seconds to sleep between logger checks.')
  parser.add_argument('--num_tries', dest='num_tries', action='store', type=int,
                      default=DEFAULT_NUM_TRIES,
                      help='Number of times to retry failed loggers.')
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  parser.add_argument('-V', '--logger_verbosity', dest='logger_verbosity',
                      default=0, action='count',
                      help='Increase output verbosity of component loggers')
  args = parser.parse_args()
  
  server = LoggerServer(interval=args.interval, num_tries=args.num_tries,
                        verbosity=args.verbosity,
                        logger_verbosity=args.logger_verbosity)
  server.start()
  
