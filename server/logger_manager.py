#!/usr/bin/env python3
"""LoggerManagers get their desired state of the world via a ServerAPI
instance and attempt to start/stop loggers with the desired configs
by dispatching requests to a local LoggerRunner.

To run the LoggerManager from the command line with (using the default
of an InMemoryServerAPI):

  server/logger_manager.py

If an initial configuration is specified on the command line, as
below:

  server/logger_manager.py --config test/configs/sample_cruise.yaml

the configuration will be loaded and set to its default mode. If a
--mode argument is included, it will be used in place of the default
mode.

By default, the LoggerManager will initialize a command line API that
reads from stdin. If logger_manager.py is to be run in a context
where stdin is not available (i.e. as part of a script), then it
should be called with the --no-console flag.

The -v flag may be specified on any of the above command lines to
increase diagnostic verbosity to "INFO". Repeating the flag sets
verbosity to "DEBUG".

For the LoggerManager and LoggerRunner, the -V (capitalized) flag
increases verbosity of the loggers being run.

Typing "help" at the command prompt will list available commands.

#######################################################
To try out the scripts, open four(!) terminal windows.

1. In the first terminal, start the LoggerManager.

2. The sample configuration that we're going to load and run is
   configured to read from simulated serial ports. To create those
   simulated ports and start feeding data to them, use a third
   terminal window to run:

   logger/utils/simulate_serial.py --config test/serial_sim.yaml -v

3. Finally, we'd like to be able to easily glimpse the data that the
   loggers are producing. The sample configuration tells the loggers
   to write to UDP port 6224 when running, so use the fourth terminal
   to run a Listener that will monitor that port. The '-' filename
   tells the Listener to write to stdout (see listen.py --help for all
   Listener options):

   logger/listener/listen.py --network :6224 --write_file -

4. Whew! Now try a few commands in the terminal running the
   LoggerManager (you can type 'help' for a full list):

   # Load a cruise configuration

   command? load_configuration test/configs/sample_cruise.yaml

   # Change cruise modes

   command? get_modes
     Modes for NBP1700: off, port, underway

   command? set_active_mode port
     (You should notice data appearing in the Listener window.)

   command? set_active_mode underway
     (You should notice more data appearing in the Listener window, and
      the LoggerRunner in the second window should leap into action.)

   command? set_active_mode off

   # Manually change logger configurations

   command? get_loggers
     Loggers: knud, gyr1, mwx1, s330, eng1, rtmp

   command? get_logger_configs s330
     Configs for s330: s330->off, s330->net, s330->file/net/db

   command? set_active_logger_config s330 s330->net

   command? set_active_mode off

   command? quit

   When setting the mode to port, you should notice data appearing in
   the listener window, and should see diagnostic output in the
   LoggerManager window.

   When setting the mode to underway, you should see more data
   appearing in the listener window (due to more logger configs
   running), and should see the LoggerRunner leap into action as the
   LoggerManager dispatches the configs for "knud.host" to it.

"""
import asyncio
import getpass  # to get username
import json
import logging
import os
import pprint
import queue
import signal
import socket  # to get hostname
import sys
import threading
import time
from urllib.parse import unquote

from os.path import dirname, realpath; sys.path.append(dirname(dirname(realpath(__file__))))

from logger.utils.read_config import read_config
from logger.utils.stderr_logging import setUpStdErrLogging, StdErrLoggingHandler
from logger.writers.text_file_writer import TextFileWriter
from logger.writers.network_writer import NetworkWriter
from server.server_api import ServerAPI
from server.logger_runner import LoggerRunner

# Number of times we'll try a failing logger before giving up
DEFAULT_MAX_TRIES = 3

SOURCE_NAME = 'LoggerManager'
USER = getpass.getuser()
HOSTNAME = socket.gethostname()

############################
def kill_handler(self, signum):
  """Translate an external signal (such as we'd get from os.kill) into a
  KeyboardInterrupt, which will signal the start() loop to exit nicely."""
  raise KeyboardInterrupt('Received external kill signal')

############################
# ! Also broadcast LoggingHandler messages to wherever?
# ! Also send level of status message in broadcast?
class WriteToAPILoggingHandler(logging.Handler):
  """Allow us to save Python logging.* messages to API backing store."""
  def __init__(self, api):
    super().__init__()

    API_LOGGING_FORMAT = '%(filename)s:%(lineno)d %(message)s'    
    self.api = api
    self.formatter = logging.Formatter(API_LOGGING_FORMAT)

  def emit(self, record):
    self.api.message_log(source='Logger', user='(%s@%s)' % (USER, HOSTNAME),
                         log_level=record.levelno,
                         message=self.formatter.format(record))

################################################################################
class LoggerManager:
  ############################
  def __init__(self, api=None, broadcast_status=None,
               interval=0.5, max_tries=3,
               logger_log_level=logging.WARNING):
    """Read desired/current logger configs from Django DB and try to run the
    loggers specified in those configs.

    api - ServerAPI (or subclass) instance by which LoggerManager will get
          its data store updates

    broadcast_status - 'Network port on which to broadcast logger status
          updates. If cruise configuration includes a display server, this
          should match the port monitored by that server, so that clients
          can receive status updates.

    interval - number of seconds to sleep between checking/updating loggers

    max_tries - number of times to try a failed server before giving up

    logger_log_level - At what logging level our component loggers
          should operate.
    """
    # Set signal to catch SIGTERM and convert it into a
    # KeyboardInterrupt so we can shut things down gracefully.
    try:
      signal.signal(signal.SIGTERM, kill_handler)
    except ValueError:
      logging.warning('LoggerManager not running in main thread; '
                      'shutting down with Ctl-C may not work.')

    # api class must be subclass of ServerAPI
    if not issubclass(type(api), ServerAPI):
      raise ValueError('Passed api "%s" must be subclass of ServerAPI' % api)
    self.api = api
    self.interval = interval
    self.max_tries = max_tries
    self.logger_log_level = logger_log_level

    # Have we been given a network port on which to broadcast status updates?
    if broadcast_status:
      self.status_writer = NetworkWriter(broadcast_status)
    else:
      self.status_writer = None

    self.quit_flag = False

    # Keep track of old configs so we only send updates to the
    # LoggerRunners when things change.
    self.old_configs = {}
    self.config_lock = threading.Lock()

    self.update_configs_thread = None

    # If so, we're going to want to make sure it and our LoggerRunner
    # (run in a separate thread) can use the same event loop
    self.event_loop = asyncio.get_event_loop()

  ############################
  def start(self):
    """Start the threads that make up the LoggerManager operation: a local
    LoggerRunner, the configuration update loop and optionally a
    thread to broadcast logger statuses. Start all threads as daemons
    so that they'll automatically terminate if the main thread does.
    """
    # Start the local LoggerRunner in its own thread.
    local_logger_thread = threading.Thread(
      target=self.local_logger_runner, daemon=True)
    local_logger_thread.start()

    # Update configs in a separate thread.
    self.update_configs_thread = threading.Thread(
      target=self.update_configs_loop, daemon=True)
    self.update_configs_thread.start()

    # If broadcasting our status, start doing that in a separate thread.
    if self.status_writer:
      self.broadcast_status_thread = threading.Thread(
        target=self._broadcast_status_loop, daemon=True)
      self.broadcast_status_thread.start()

  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True
    self.logger_runner.quit()

  ##########################
  def local_logger_runner(self):
    """Create and run a local LoggerRunner."""
    # Some of the loggers may require an event loop. We're running in
    # a separate thread, so we need to explicitly set our event loop,
    # using the one we stored during init().
    self.logger_runner = LoggerRunner(max_tries=self.max_tries,
                                      event_loop=self.event_loop,
                                      logger_log_level=self.logger_log_level)
    # Instead of calling the LoggerRunner.run(), we iterate ourselves,
    # doing updates to retrieve status reports.
    while not self.quit_flag:
      status = self.logger_runner.check_loggers(manage=True, clear_errors=False)
      message = {'status': status}
      self._process_logger_runner_message(message)

      time.sleep(self.interval)

  ############################
  def update_configs_loop(self):
    """Iteratively check the API for updated configs and send them to the
    appropriate LoggerRunners.
    """
    while not self.quit_flag:
      self.update_configs()
      time.sleep(self.interval)

  ############################
  def update_configs(self):
    """Check the API for updated configs and send them to the LoggerRunner.
    """
    # Get latest configs. The call will throw a value error if no
    # configuration is loaded.
    with self.config_lock:
      try:
        new_configs = self.api.get_logger_configs()
      except (AttributeError, ValueError):
        return

      # If configs have changed, send updated ones to the logger_runner
      if not new_configs == self.old_configs:
        self.logger_runner.set_configs(new_configs)

  ############################
  def _broadcast_status_loop(self):
    """Iteratively grab status messages from the api and send them out as
    JSON to whatever writer we're using to broadcast our logger
    statuses. In theory we could be much more efficient and directly
    grab status updates in _process_logger_runner_messages() when we
    get them from the LoggerRunners.
    """    
    # We stash previous_configs so that we know not to send them if
    # they haven't changed since last check. We keep the raw
    # previous_status separately, because we have to do some
    # processing to get it into a form that's useful for our clients,
    # and we want do avoid doing that processing if we can.
    previous_cruise_def = {}
    previous_logger_status = {}

    while not self.quit_flag:
      # Sleep for a bit before going around (also, before we try the
      # first time, to let the LoggerManager start up).
      time.sleep(self.interval)
      
      cruise_def_changed = status_changed = False
      try:
        cruise_def = {
          'cruise':  self.api.get_configuration(),
          'loggers': self.api.get_loggers(),
          'modes':   self.api.get_modes(),
          'mode':    self.api.get_active_mode()
          }
      except (AttributeError, ValueError):
        logging.info('No cruise definition found')
        cruise_def = {}

      if not cruise_def == previous_cruise_def:
        cruise_def_changed = True
        previous_cruise_def = cruise_def

      # We expect status to be a dict of timestamp:{logger status
      # dict} entries. If we don't have any yet, work with a dummy
      # entry.
      status = self.api.get_status() or {0: {}}
      timestamp = 0
      logger_status = {}
      for next_timestamp, next_logger_status in status.items():
        timestamp = max(timestamp, next_timestamp)
        logger_status.update(next_logger_status)

      # Has anything changed with logger statuses?
      if not logger_status == previous_logger_status:
        previous_logger_status = logger_status
        status_changed = True

      #########
      # If nothing has changed, just send a heartbeat timestamp
      if not cruise_def_changed and not status_changed:
        status_message = {'data_id':'logger_status',
                          'timestamp': timestamp,
                          'fields': {}}
        self.status_writer.write(json.dumps(status_message))
        continue

      #########
      # If we're here, something changed, either in cruise definition
      # or status; send out updates for all in small packets.

      # Send cruise metadata
      cruise = cruise_def['cruise']
      status_message = {'data_id':'cruise_metadata',
                        'timestamp': timestamp,
                        'fields': {
                          'status:cruise_id': cruise.id,
                          'status:cruise_start': cruise.start.timestamp(),
                          'status:cruise_end': cruise.end.timestamp(),
                          'status:cruise_loaded': cruise.loaded_time.timestamp(),
                          'status:cruise_filename': cruise.config_filename,
                        }}
      self.status_writer.write(json.dumps(status_message))

      # Send list of loggers
      loggers = cruise_def['loggers']
      status_message = {'data_id':'logger_status',
                        'timestamp': timestamp,
                        'fields': {'status:logger_list':
                                   [logger for logger in loggers]}}
      self.status_writer.write(json.dumps(status_message))

      # Send list of modes and current mode
      status_message = {'data_id':'logger_status',
                        'timestamp': timestamp,
                        'fields': {'status:mode_list': cruise_def['modes'],
                                   'status:mode': cruise_def['mode']}}
      self.status_writer.write(json.dumps(status_message))

      # Send one logger status per message, so we don't blow past the
      # packet size limit if we're broadcasting UDP
      for logger in loggers:
        status = logger_status.get(logger, None)
        if not status:
          logging.warning('Skipping logger %s', logger)
          continue        
        status_message = {
          'data_id':'logger_status',
          'timestamp': timestamp,
          'fields': {
            'status:logger:' + logger: {
              'configs': loggers[logger].get('configs', []),
              'config': status.get('config', None),
              'failed': status.get('failed', None),
              'running': status.get('running', None)
            }
          }
        }
        self.status_writer.write(json.dumps(status_message))

  ##########################
  def _process_logger_runner_message(self, message):
    """Process a message received from a LoggerRunner. We expect
    message to be a dict of
    {
      'status': {
        logger_id: {errors: [], running,  failed},
        logger_id: {...},
        logger_id: {...}
      },
      'errors': {}   # if any errors to report
    }
    """
    logging.debug('LoggerRunner sent fields: %s', ', '.join(message.keys()))
    status = message.get('status', None)
    errors = message.get('errors', None)
    if status:
      self.api.update_status(status)
    if errors:
      logging.error('Errors from LoggerRunner: %s', errors)

################################################################################
################################################################################
if __name__ == '__main__':
  import argparse
  import atexit
  import readline

  from server.server_api_command_line import ServerAPICommandLine

  parser = argparse.ArgumentParser()
  parser.add_argument('--config', dest='config', action='store',
                      help='Name of configuration file to load.')
  parser.add_argument('--mode', dest='mode', action='store', default=None,
                      help='Optional name of mode to start system in.')

  parser.add_argument('--database', dest='database', action='store',
                      choices=['memory', 'django', 'hapi'],
                      default='memory', help='What backing store database '
                      'to use.')

  parser.add_argument('--broadcast_status', dest='broadcast_status',
                      action='store', default=None,
                      help='Network port on which to broadcast logger status '
                      'updates. If cruise configuration includes a display '
                      'server, this should match the port monitored by that '
                      'server, so that clients can receive status updates.')

  parser.add_argument('--interval', dest='interval', action='store',
                      type=float, default=1,
                      help='How many seconds to sleep between logger checks.')
  parser.add_argument('--max_tries', dest='max_tries', action='store', type=int,
                      default=DEFAULT_MAX_TRIES,
                      help='Number of times to retry failed loggers.')

  parser.add_argument('--no-console', dest='no_console', default=False,
                      action='store_true', help='Run without a console '
                      'that reads commands from stdin.')

  parser.add_argument('--stderr_file', dest='stderr_file', default=None,
                      help='Optional file to which stderr messages should '
                      'be written.')
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  parser.add_argument('-V', '--logger_verbosity', dest='logger_verbosity',
                      default=0, action='count',
                      help='Increase output verbosity of component loggers')
  args = parser.parse_args()

  # Set up logging first of all
  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  log_level = LOG_LEVELS[min(args.verbosity, max(LOG_LEVELS))]
  setUpStdErrLogging(log_level=log_level)
  if args.stderr_file:
    stderr_writers = [TextFileWriter(args.stderr_file)]
    logging.getLogger().addHandler(StdErrLoggingHandler(stderr_writers))
    
  # What level do we want our component loggers to write?
  logger_log_level = LOG_LEVELS[min(args.logger_verbosity, max(LOG_LEVELS))]

  ############################
  # Instantiate API - a Are we using an in-memory store or Django
  # database as our backing store? Do our imports conditionally, so
  # they don't actually have to have Django if they're not using it.
  if args.database == 'django':
    from django_gui.django_server_api import DjangoServerAPI
    api = DjangoServerAPI()
  elif args.database == 'memory':
    from server.in_memory_server_api import InMemoryServerAPI
    api = InMemoryServerAPI()
  elif args.database == 'hapi':
    from hapi.hapi_server_api import HapiServerAPI
    api = HapiServerAPI()
  else:
    raise ValueError('Illegal arg for --database: "%s"' % args.database)

  # Now that API is defined, tack on one more logging handler: one
  # that passes messages to API.
  # TODO: decide if we even need this.
  logging.getLogger().addHandler(WriteToAPILoggingHandler(api))

  ############################
  # Create our LoggerManager
  logger_manager = LoggerManager(api=api,
                                 broadcast_status=args.broadcast_status,
                                 interval=args.interval,
                                 max_tries=args.max_tries,
                                 logger_log_level=logger_log_level)

  # Register a callback: when api.set_active_mode() or api.set_config()
  # have completed, they call api.signal_update(). We're registering
  # update_configs() with the API so that it gets called when the api
  # signals that an update has occurred.
  api.on_update(callback=logger_manager.update_configs)
  api.on_quit(callback=logger_manager.quit)

  ############################
  # Start all the various LoggerManager threads running
  logger_manager.start()

  ############################
  # If they've given us an initial configuration, get and load it.
  if args.config:
    config = read_config(args.config)
    api.load_configuration(config)
    api.message_log(source=SOURCE_NAME, user='(%s@%s)' % (USER, HOSTNAME),
                    log_level=api.INFO,
                    message='started with: %s' % args.config)
  if args.mode:
    if not args.config:
      raise ValueError('Argument --mode can only be used with --config')
    api.set_active_mode(args.mode)
    api.message_log(source=SOURCE_NAME, user='(%s@%s)' % (USER, HOSTNAME),
                    log_level=api.INFO,
                    message='initial mode (%s@%s): %s' % (USER, HOSTNAME, args.mode))

  try:
    # If no console, just wait for the configuration update thread to
    # end as a signal that we're done.
    if args.no_console:
      logging.warning('--no-console specified; waiting for LoggerManager '
                   'to exit.')
      if logger_manager.update_configs_thread:
        logger_manager.update_configs_thread.join()
      else:
        logging.warning('LoggerManager has no update_configs_thread? '
                        'Exiting...')

    else:
      # Create reader to read/process commands from stdin. Note: this
      # needs to be in main thread for Ctl-C termination to be properly
      # caught and processed, otherwise interrupts go to the wrong places.

      # Set up command line interface to get commands. Start by
      # reading history file, if one exists, to get past commands.
      hist_filename = '.openrvdas_logger_manager_history'
      hist_path = os.path.join(os.path.expanduser('~'), hist_filename)
      try:
        readline.read_history_file(hist_path)
        # default history len is -1 (infinite), which may grow unruly
        readline.set_history_length(1000)
      except (FileNotFoundError, PermissionError):
        pass
      atexit.register(readline.write_history_file, hist_path)

      command_line_reader = ServerAPICommandLine(api=api)
      command_line_reader.run()

  except KeyboardInterrupt:
    pass
  logging.debug('Done with logger_manager.py - exiting')
