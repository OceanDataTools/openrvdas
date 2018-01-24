#!/usr/bin/env python3
"""Run loggers.

Typical use:

  # Create an expanded configuration
  logger/utils/build_config.py --config test/configs/sample_cruise.json > config.json

  # Run the loggers from the "underway" mode of that configuration
  logger/utils/run_loggers.py --config config.json --mode underway -v

(To get this to work using the sample config sample_cruise.json above,
sample_cruise.json, you'll also need to run

  logger/utils/serial_sim.py --config test/serial_sim.py

in a separate terminal window to create the virtual serial ports the
sample config references and feed simulated data through them.)

You can also run with the --interactive flag, in which case you can,
at any point, type the name of a mode into the terminal window the
controller will switch to that mode:

  logger/utils/run_loggers.py --config config.json --interactive

At the moment, --interactive is a bit messy, as user input is liable
to be interspersed with logging output, making it difficult to see the
state that's being typed in.

"""

import argparse
import logging
import multiprocessing
import pprint
import signal
import sys
import time
import threading

sys.path.append('.')

from logger.utils.build_config import BuildConfig
from logger.utils.read_json import read_json
from logger.listener.listen import ListenerFromConfig

run_logging = logging.getLogger(__name__)

################################################################################
class LoggerRunner:
  ############################
  def __init__(self, config, mode=None, interactive=False, interval=0.5):
    """Create a LoggerRunner.
    
    config - Python dict containing complete set of logger configurations.

    mode -   Optional string indicating which mode the LoggerRunner should
             begin in.

    interactive - take terminal input to select modes

    interval - number of seconds to sleep between checking/updating loggers
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

    # Map logger name to config and to the process running it
    self.configs = {}
    self.processes = {}

    self.interactive = interactive
    self.interval = interval
    self.mode_change_lock = threading.Lock()
    self.quit_flag = False
    
  ############################
  def _check_loggers(self, desired_configs):
    """Start up all the loggers using the configuration specified in
    the current mode."""

    # All loggers, whether in current configuration or desired mode.
    loggers = set(self.configs.keys()).union(desired_configs.keys())
    for logger in loggers:
      current_config = self.configs.get(logger, None)
      desired_config = desired_configs.get(logger, None)

      # Isn't running and shouldn't be running. Nothing to do here
      if current_config is None and desired_config is None:
        continue
      
      # If current_config == desired_config (and is not None) and the
      # process is running, all is right with the world; skip to next.
      process = self.processes.get(logger)
      if current_config == desired_config:
        if process.is_alive():
          continue
        else:
          run_logging.warning('Process for "%s" unexpectedly dead!', logger)

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
      if desired_config:
        run_logging.info('Starting up new process for %s', logger)
        self.processes[logger] = self._start_logger(desired_config)

  ############################
  def set_mode(self, mode):
    """Change the mode of the running loggers."""

    modes = self.configuration.get('modes', None)
    if not mode in modes:
      run_logging.error('Mode "%s" is not valid mode. Modes are %s or "quit"',
                        mode, ', '.join(['"%s"' % m for m in modes.keys()]))
      return

    # For now, the lock isn't srictly necessary; mostly a reminder
    # that we ought to be careful about what happens when modes
    # change.
    with self.mode_change_lock:
      run_logging.info('Switching to mode %s', mode)
      self.mode = mode
        
  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True

  ############################
  def _start_logger(self, config):
    """Create a new process running a Listener/Logger using the passed
    config, and return the Process object."""

    run_logging.debug('Starting config:\n%s', pprint.pformat(config))
    listener = ListenerFromConfig(config)
    proc = multiprocessing.Process(target=listener.run)
    proc.start()
    return proc

  ############################
  def _get_new_mode(self):
    """Create a new process running a Listener/Logger using the passed
    config, and return the Process object."""

    ################
    class ReaderTimeout(StopIteration):
      """A custom exception we can raise when we hit timeout."""
      pass
    
    ################
    def _timeout_handler(signum, frame):
      """If timeout fires, raise our custom exception"""
      run_logging.debug('Read operation timed out')
      raise ReaderTimeout

    ################
    # Set timeout we can catch if things are taking too long
    signal.signal(signal.SIGALRM, _timeout_handler)    
    signal.alarm(3)
    new_mode = None
    try:
      new_mode = input()
    except ReaderTimeout:
      pass
    signal.alarm(0)     # Disable the signal

    # If no new_mode, we got no input before timeout - go home
    if not new_mode:
      return

    # We got something - it should either be 'quit' or a new mode
    if new_mode == 'quit':
      self.quit_flag = True
    else:
      self.set_mode(new_mode)

  ############################
  def run(self):
    """Start up all the loggers using the configuration specified in
    the current mode, loop and keep checking them."""

    while not self.quit_flag:

      with self.mode_change_lock:
        # Dict of configs for loggers we're *supposed* to be running
        desired_configs = self.configuration.get('modes').get(self.mode)

      run_logging.info('Checking logger states against mode "%s"', self.mode)
      self._check_loggers(desired_configs)

      run_logging.debug('Sleeping %s seconds...', self.interval)
      time.sleep(self.interval)

      if self.interactive:
        self._get_new_mode()

    # If here, we've dropped out of the "while not quit" loop. Launch
    # a new (empty) desired configuration in which nothing is running
    # prior to exiting.
    run_logging.info('Received quit request - shutting loggers down.')
    self._check_loggers({})

################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('--config', dest='config', action='store', required=True,
                      help='Name of configuration file to load and expand.')
  parser.add_argument('--mode', dest='mode', action='store', default=None,
                      help='Optional name of mode to start system in.')
  parser.add_argument('--interactive', dest='interactive', action='store_true',
                      help='Whether to interactively accept mode changes from '
                      'the command line.')
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

  # Verbosity of our component loggers (and everything else)
  args.logger_verbosity = min(args.logger_verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.logger_verbosity])

  config_json = read_json(args.config)

  runner = LoggerRunner(config=config_json, mode=args.mode,
                        interactive=args.interactive, interval=args.interval)
  runner.run()
