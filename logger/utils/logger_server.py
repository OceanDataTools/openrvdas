#!/usr/bin/env python3
"""Run loggers using modes/configurations from the Django database.

Typically invoked via the web interface:

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
import os
import pprint
import sys
import threading
import time

sys.path.append('.')

from logger.utils.read_json import read_json
from logger.utils.logger_manager import LoggerManager, run_logging
from logger.utils.server_api import ServerAPI

from logger.utils.server_api import InMemoryServerAPI

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

# Number of times we'll try a failing logger before giving up
DEFAULT_MAX_TRIES = 3

################################################################################
class LoggerServer:
  ############################
  def __init__(self, api=None, interval=0.5, max_tries=3,
               verbosity=0, logger_verbosity=0):
    """Read desired/current logger configs from Django DB and try to run the
    loggers specified in those configs.

    api - ServerAPI (or subclass) instance by which LoggerServer will get
          its data store updates
    interval - number of seconds to sleep between checking/updating loggers

    max_tries - number of times to try a failed server before giving up
    """    

    # api must be of a type that's a subclass of ServerAPI
    if not issubclass(type(api), ServerAPI):
      raise ValueError('Passed api "%s" must be subclass of ServerAPI' % api)
    self.api = api
    
    # kill off all running loggers from the previous current cruise.
    self.current_cruise_timestamp = None
    self.interval = interval
    self.max_tries = max_tries
    self.quit_flag = False

    # We will have one LoggerManager per cruise, maintained in a dict
    # of {cruise_id: LoggerManager,...}. We'll instantiate them on the
    # fly, as we're asked to manage cruises.
    self.logger_manager = {}

    # Set up logging levels for both ourselves and for the loggers we
    # start running. Attach a Handler that will write log messages to
    # Django database.
    logging.basicConfig(format=LOGGING_FORMAT)

    log_verbosity = LOG_LEVELS[min(verbosity, max(LOG_LEVELS))]
    log_logger_verbosity = LOG_LEVELS[min(logger_verbosity, max(LOG_LEVELS))]
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
    errors, it means the LoggerManager

    """

    # Rather than relying on our LoggerManager to loop and check
    # loggers, we do it ourselves, so that we can update statuses and
    # errors in the Django database.
    old_configs = {}

    try:
      while not self.quit_flag:
        status = {}
        for cruise_id in api.get_cruises():
          # Do we have a LoggerManager for this cruise yet?
          if not cruise_id in self.logger_manager:
            self.logger_manager[cruise_id] = LoggerManager(
              interval=self.interval, max_tries=self.max_tries)
          logger_manager = self.logger_manager[cruise_id]
          
          # Get the most recent configs for this cruise. If they have
          # changed since last time, tell the LoggerManager to shut
          # down old configs and start new ones.
          configs = api.get_configs(cruise_id)
          if not cruise_id in old_configs:
            old_configs[cruise_id] = {}

          if configs != old_configs[cruise_id]:
            logging.warning('Got updated configs for %s', cruise_id)
            logger_manager.set_configs(configs)
            old_configs[cruise_id] = configs

          # Now check up on status of all loggers that are supposed to be
          # running. Because manage=True, we'll restart those that are
          # supposed to be but aren't. We'll get a dict of
          #
          # { logger_id: {errors: [], running,  failed},
          #   logger_id: {...}, 
          #   logger_id: {...}
          # }
          status[cruise_id] = logger_manager.check_loggers(manage=True,
                                                           clear_errors=True)

        # Write the returned statuses to data store
        api.update_status(status)

        # Nap for a bit before checking again
        time.sleep(self.interval)

    except KeyboardInterrupt:
      logging.warning('LoggerServer received keyboard interrupt - '
                      'trying to shut down nicely.')

    # Set all LoggerManagers to empty configs to shut down all their loggers
    [logger_manager.set_configs({})
     for cruise_id, logger_manager in self.logger_manager.items()]

  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True


  

################################################################################
if __name__ == '__main__':
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument('--config', dest='config', action='store', required=True,
                      help='Name of cruise configuration file to load.')

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

  api = InMemoryServerAPI()
  logger_server = LoggerServer(api=api, interval=args.interval,
                               max_tries=args.max_tries,
                               verbosity=args.verbosity,
                               logger_verbosity=args.logger_verbosity)
  logger_server_thread = threading.Thread(target=logger_server.run)
  logger_server_thread.start()

  # Get and load the cruise config we'll be running (for now, just one
  # cruise config).
  cruise_config = read_json(args.config)
  api.load_cruise(cruise_config)

  # Simplifying assumption: we've got exactly one cruise loaded
  cruise_id = api.get_cruises()[0]
  modes = api.get_modes(cruise_id)
  
  # Loop, trying new modes, until we receive a keyboard interrupt
  try:
    while True:
      print(' mode?: ')
      new_mode = input()

      if new_mode == 'quit':
        break

      # Print last 10 statuses
      if new_mode == 'status':
        for (timestamp, status) in api.status[-10:]:
          print('%f: %s' % (timestamp, status))
        continue

      if not new_mode in modes:
        logging.error('Config file "%s" has no mode "%s"' %
                      (args.config, new_mode))
        logging.error('Valid modes are "%s" and "quit".', '", "'.join(modes))
      else:
        logging.warning('#### Setting mode to %s', new_mode)
        api.set_mode(cruise_id, new_mode)

  # On keyboard interrupt, break from our own loop and signal the
  # run() thread that it should clean up and terminate.
  except KeyboardInterrupt:
    pass

  logger_server.quit()
  logger_server_thread.join()
  
  
