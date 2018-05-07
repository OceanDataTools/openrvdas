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
#import threading
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

from server.logger_manager import LoggerRunner, run_logging

TIME_FORMAT = '%Y-%m-%d:%H:%M:%S'

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

# Number of times we'll try a failing logger before giving up
DEFAULT_MAX_TRIES = 3

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
  def __init__(self, interval=0.5, max_tries=3,
               verbosity=0, logger_verbosity=0):
    """Read desired/current logger configs from Django DB and try to run the
    loggers specified in those configs.

    interval - number of seconds to sleep between checking/updating loggers

    max_tries - number of times to try a failed server before giving up
    """    

    self.logger_runner = LoggerRunner(interval=interval, max_tries=max_tries)

    # Instead of running the LoggerRunner.run() in a separate thread,
    # we'll manually call its check_logger() method in our own run()
    # method.

    #self.logger_runner_thread = threading.Thread(target=self.logger_runner.run)

    # If new current cruise is loaded, we want to notice and politely
    # kill off all running loggers from the previous current cruise.
    self.current_cruise_timestamp = None
    self.interval = interval
    self.quit_flag = False

    # Set up logging levels for both ourselves and for the loggers we
    # start running. Attach a Handler that will write log messages to
    # Django database.
    logging.basicConfig(format=LOGGING_FORMAT)

    log_verbosity = LOG_LEVELS[min(verbosity, max(LOG_LEVELS))]
    log_logger_verbosity = LOG_LEVELS[min(logger_verbosity, max(LOG_LEVELS))]
    
    run_logging.addHandler(WriteToDjangoHandler('LoggerServer'))
    logging.getLogger().addHandler(WriteToDjangoHandler('LoggerServer'))

    run_logging.setLevel(log_verbosity)
    logging.getLogger().setLevel(log_logger_verbosity)
  
  ############################
  def run(self):
    """Loop, checking that loggers are in the state they should be,
    getting them into that state if they aren't, and saving the resulting
    status to a StatusUpdate record in the database.

    We get the logger running status - True (running), False (not
    running but should be) or None (not running and shouldn't be) -
    and any errors. If logger is not in state we want it and there are
    no t is not running. If logger is not running and there are no
    errors, it means the LoggerRunner

    """

    # Rather than relying on our LoggerRunner to loop and check
    # loggers, we do it ourselves, so that we can update statuses and
    # errors in the Django database.
    old_configs = {}
    old_status = {}

    try:
      while not self.quit_flag:
        loggers = Logger.objects.all()
        
        # Get the currently-specified config for each logger. If
        # things have changed, extract the JSON for the new configs
        # and send to LoggerRunner to start/stop the relevant
        # processes.

        # NOTE: we key off of logger id instead of logger name for the
        # config dict. We do this because we may have multiple cruises
        # with overlapping logger names loaded at the same time.
        configs = {logger.id:logger.config for logger in loggers}

        # If configs have changed, send JSON for the new configs to be run
        if not configs == old_configs:
          configs_json = {logger_id:parse_json(config.config_json)
                          for logger_id, config in configs.items() if config}
          logging.info('Configurations changed - updating.')
          logging.debug('New configurations: %s', pprint.pformat(configs))
          self.logger_runner.set_configs(configs_json)

        # Get status of loggers, including errors, telling
        # LoggerRunner to clear out old errors and start/stop any
        # loggers that aren't in the desired configuration. Returned
        # status is a dict keyed by logger id's. Value are a dict of
        #
        # {
        #   logger_id: {'errors': [],
        #               'running': True/False/None,
        #               'failed': True/False},
        #   ...
        # }
        status = self.logger_runner.check_loggers(update=True,
                                                   clear_errors=True)

        # If there's anything notable - an error or change of state -
        # create a new LoggerConfigState to document it.
        for logger_id, logger_status in status.items():
          config = configs.get(logger_id, None)
          old_config = old_configs.get(logger_id, None)
          old_logger_status = old_status.get(logger_id, {})

          try:
            logger = Logger.objects.get(id=logger_id)
          except Logger.DoesNotExist:
            logging.warning('No logger corresponding to id %d?!?', logger_id)
            continue
          
          if (logger_status.get('errors', None) or
              logger_status != old_logger_status or
              config != old_config):
            running = bool(logger_status.get('running', False))
            errors = ', '.join(logger_status.get('errors', []))
            pid = logger_status.get('pid', None)
            logging.info('Updating %s config: %s; running: %s, errors: %s',
                         logger, config.name if config else '-none-',
                         running, errors or 'None')
            LoggerConfigState(logger=logger, config=config, running=running,
                              process_id=pid, errors=errors).save()
            
        # Cache what we've observed so that we can tell what has
        # changed next time around.
        old_configs = configs
        old_status = status

        # Nap for a bit before checking again
        time.sleep(self.interval)

    except KeyboardInterrupt:
      logging.warning('LoggerServer received keyboard interrupt - '
                      'trying to shut down nicely.')

    # Set LoggerRunner to empty configs to shut down all its loggers
    self.logger_runner.set_configs({})
    
    # Tell the LoggerRunner to stop and wait for its thread to exit
    #self.logger_runner.quit()
    #self.logger_runner_thread.join()

  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True

################################################################################
if __name__ == '__main__':
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument('--interval', dest='interval', action='store',
                      type=float, default=1,
                      help='How many seconds to sleep between logger checks.')
  parser.add_argument('--max_tries', dest='max_tries', action='store', type=int,
                      default=DEFAULT_MAX_TRIES,
                      help='Number of times to retry failed loggers.')
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  parser.add_argument('-V', '--logger_verbosity', dest='logger_verbosity',
                      default=0, action='count',
                      help='Increase output verbosity of component loggers')
  args = parser.parse_args()
  
  server = LoggerServer(interval=args.interval, max_tries=args.max_tries,
                        verbosity=args.verbosity,
                        logger_verbosity=args.logger_verbosity)
  server.run()
  
