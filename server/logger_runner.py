#!/usr/bin/env python3
"""Low-level class to start/stop loggers according passed in
definitions and commands.

Typically used by a higher-level class like LoggerManager

Typical use:

  # Run the loggers from the "underway" mode of that configuration
  server/logger_manager.py --config test/configs/sample_cruise.json \
      --mode underway

(To get this to work using the sample config sample_cruise.json above,
you'll also need to run

  logger/utils/serial_sim.py --config test/serial_sim.py

in a separate terminal window to create the virtual serial ports the
sample config references and feed simulated data through them.)

Be advised that the command line script is intentionally just a
rudimentary wrapper around the LoggerRunner class. We expect that,
more often than not, the LoggerRunner class will be used directly by
other code, such as a LoggerServer, which can exercise its full
powers.

"""
import argparse
import json
import logging
import multiprocessing
import pprint
import signal
import sys
import time
import threading

sys.path.append('.')

from logger.utils.read_json import read_json
from logger.listener.listen import ListenerFromLoggerConfig

run_logging = logging.getLogger(__name__)

############################
def kill_handler(self, signum):
  """Translate an external signal (such as we'd get from os.kill) into a
  KeyboardInterrupt, which will signal the start() loop to exit nicely."""
  logging.info('Received external kill')
  raise KeyboardInterrupt('Received external kill signal')

################################################################################
class LoggerRunner:
  ############################
  def __init__(self, interval=0.5, max_tries=3, initial_configs=None):
    """Create a LoggerRunner.
    interval - number of seconds to sleep between checking/updating loggers

    max_tries - number of times to retry a dead logger config

    initial_configs - optional dict of configs to start up on creation.
    """
    # Map logger name to config, process running it, and any errors
    self.logger_configs = {}
    self.processes = {}
    self.errors = {}
    self.num_tries = {}
    self.failed_loggers = set()

    self.interval = interval
    self.max_tries = max_tries
    self.quit_flag = False
      
    # Set the signal handler so that an external break will get
    # translated into a KeyboardInterrupt. But signal only works if
    # we're in the main thread - catch if we're not, and just assume
    # everything's gonna be okay and we'll get shut down with a proper
    # "quit()" call othewise.
    try:
      signal.signal(signal.SIGTERM, kill_handler)
    except ValueError:
      logging.warning('LoggerRunner not running in main thread; '
                      'shutting down with Ctl-C may not work.')

    # Don't let other threads mess with data while we're
    # messing. Re-entrant so that we don't have to worry about
    # re-acquiring when, for example set_configs() calls set_config().
    self.config_lock = threading.RLock()

    # Only let one call to check_loggers() proceed at a time
    self.check_loggers_lock = threading.Lock()
    
    # If we were given any initial configs, set 'em up
    if initial_configs:
      self.set_configs(initial_configs)

  ############################
  def set_config(self, logger, new_config):
    """Start/stop individual logger to put into new config.
    
    logger - name of logger

    new_config - dict containing Listener configuration.
    """
    logging.info('Setting logger %s to config %s', logger,
                 new_config.get('name', 'Unknown') if new_config else None)

    with self.config_lock:
      current_config = self.logger_configs.get(logger, None)

      # Isn't running and shouldn't be running. Nothing to do here
      if current_config is None and new_config is None:
        return

      # If current_config == new_config (and is not None) and the
      # process is running, all is right with the world; skip to next.
      process = self.processes.get(logger, None)
      if current_config == new_config:
        if process and process.is_alive():
          return
        else:
          warning = 'Process for "%s" unexpectedly dead!' % logger
          run_logging.warning(warning)
          self.errors[logger].append(warning)

      # Either old and new config don't match or process is dead. If
      # process isn't dead, then it means old and new config don't
      # match. So kill old process before starting new one.
      elif process:
        self._kill_logger(logger)

      # Finally, if we have a new config, start up the new process for it
      if new_config:
        run_logging.info('Starting up new process for %s', logger)
        self._start_logger(logger, new_config)
        self.num_tries[logger] = 1
      
  ############################
  def set_configs(self, new_configs):
    """Start/stop loggers as necessary to move from current configs
    to new configs.

    new_configs - a dict of {logger_name:config} for all loggers that
                  should be running
    """    
    # All loggers, whether in current configuration or desired mode.
    with self.config_lock:
      # If loggers we know about are no longer part of new config,
      # shut them down and delete them. Note that this is different
      # from the logger having an empty/None configuration, which
      # means we should shut it down, but we still remember it.
      disappearing_loggers = set(self.logger_configs) - set(new_configs)
      if disappearing_loggers:
        logging.info('New configuration contains no mention of some '
                    'loggers. Shutting down and deleting: %s',
                     disappearing_loggers)
        for logger in disappearing_loggers:
          self._kill_and_delete_logger(logger)
          
      # Now set all the other loggers in their new configs. This
      # includes starting them up if new config is running and
      # shutting them down if it isn't.
      for logger, config in new_configs.items():
        self.set_config(logger, config)
  
  ############################
  def _start_logger(self, logger, config):
    """Create a new process running a Listener/Logger using the passed
    config, and return the Process object."""

    try:
      run_logging.debug('Starting config:\n%s', pprint.pformat(config))
      listener = ListenerFromLoggerConfig(config)

      proc = multiprocessing.Process(target=listener.run)
      proc.start()
      errors = []

    # If something went wrong. If it was a KeyboardInterrupt, signal
    # everybody to quit. Otherwise stash error and return None
    except Exception as e:
      if e is KeyboardInterrupt:
        self.quit()
        return

      logging.warning('Config %s got exception: %s', config['name'], str(e))
      proc = None
      errors = [str(e)]

    # Store the new setup (or the wreckage, depending)
    with self.config_lock:
      self.logger_configs[logger] = config
      self.processes[logger] = proc
      self.errors[logger] = errors
      self.failed_loggers.discard(logger)

  ############################
  def _kill_logger(self, logger):
    """Kill the process associated with this logger and clean out
    the data associated with it."""
    with self.config_lock:
      process = self.processes.get(logger, None)
      if process:
        run_logging.info('Shutting down process for %s', logger)
        process.terminate()
        process.join()
      else:
        logging.info('Attempted to kill process for %s, but no '
                     'associated process found.', logger)

    # Clean out debris from old logger process
    self.logger_configs[logger] = None
    self.processes[logger] = None
    self.errors[logger] = []
    self.failed_loggers.discard(logger)

  ############################
  def _kill_and_delete_logger(self, logger):
    """Not only kill the logger, but remove all trace of it from memory."""
    self._kill_logger(logger)

    # Clean out debris from old logger process
    if logger in self.logger_configs: del self.logger_configs[logger]
    if logger in self.processes: del self.processes[logger]
    if logger in self.errors: del self.errors[logger]
    self.failed_loggers.discard(logger)
    
  ############################
  def check_logger(self, logger, manage=False, clear_errors=False):
    """Check whether passed logger is in state it should be. Restart/stop it 
    as appropriate. Return True if logger is in desired state.

    logger - name of logger to check.

    manage - if True, and if logger isn't in state it's supposed to be,
             try restarting it.
    clear_errors - if True, clear out accumulated error messages.
    """
    with self.config_lock:
      config = self.logger_configs.get(logger, None)
      process = self.processes.get(logger, None)

      # Now figure out whether we are (and should be) running.
      
      # Not running and shouldn't be. We're good.
      if config is None and process is None:
        running = None

      # If we are running and are supposed to be, also good.
      elif config and process and process.is_alive():
        running = True

      # Shouldn't be running, but is?!?
      elif not config and process:
        run_logging.warning('Logger %s shouldn\'t be running, but is?', logger)
        running = True
        if manage:
          self._kill_logger(logger)
          process = None

      # Here if it should be running, but isn't.
      else:
        running = False
        
        # If we're supposed to try and manage the state ourselves,
        # restart dead logger.
        if manage:
          # If we've tried restarting max_tries times, give up and
          # consider logger to have failed.
          if logger in self.failed_loggers:
            logging.debug('Logger %s failed %d times; not retrying',
                          logger, self.max_tries)
          elif self.num_tries[logger] == self.max_tries:
            self.failed_loggers.add(logger)
            run_logging.warning('Logger %s has failed %d times; not retrying',
                                logger, self.max_tries)
          else:
            # If we've not used up all our tries, try starting it again
            warning = 'Process for %s unexpectedly dead; restarting' % logger
            run_logging.warning(warning)
            self.errors[logger].append(warning)
            self._start_logger(logger, self.logger_configs[logger])
            self.num_tries[logger] += 1

      status = {
        'errors': self.errors.get(logger, []),
        'running': running,
        'failed': logger in self.failed_loggers,
        'pid': process.pid if process else None
      }
      # Clear accumulated errors for this logger if they've asked us to
      if clear_errors:
        self.errors[logger] = []
        
    return status
    
  ############################
  def check_loggers(self, manage=False, clear_errors=False):
    """Check that all loggers are in desired states. Return map from
    logger name to Boolean, where True means logger is running and
    should be.

    manage       - if True, try to restart dead loggers.
    clear_errors - if True, clear out accumulated error messages.
    """
    with self.check_loggers_lock:
      return {logger:self.check_logger(logger, manage, clear_errors)
              for logger in self.logger_configs}

  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True

    # Set all loggers to "None" config, which should shut them down.
    # NOTE: because set_config(logger, None) deletes the logger in
    # question, we need to copy the keys into a list, otherwise we get
    # a "dictionary changed size during iteration" error.
    run_logging.info('Received quit request - shutting loggers down.')
    [self.set_config(logger, None)
     for logger in list(self.logger_configs.keys())]

  ############################
  def run(self):
    """Iterate, checking loggers, warning of problems and restarting as
    indicated."""

    # Iterate until we get 'quit'
    while not self.quit_flag:
      with self.config_lock:
        status = self.check_loggers(manage=True)
        logging.debug('Logger status: %s', str(status))

      run_logging.debug('Sleeping %s seconds...', self.interval)
      time.sleep(self.interval)


################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('--config', dest='config', action='store', default=None,
                      help='Initial set of configs to run.')
  parser.add_argument('--max_tries', dest='max_tries', action='store',
                      type=int, default=3, help='How many times to try a '
                      'crashing config before giving up on it as failed.')
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

  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'

  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

  # Our verbosity
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  run_logging.setLevel(LOG_LEVELS[args.verbosity])

  if args.config:
    initial_configs = read_json(args.config)
  else:
    initial_configs = None
    
  runner = LoggerRunner(interval=args.interval, max_tries=args.max_tries,
                        initial_configs=initial_configs)
  runner.run()

