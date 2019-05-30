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
import multiprocessing
import os
import pprint
import queue
import signal
import socket  # to get hostname
import sys
import threading
import time
import websockets

from urllib.parse import unquote

from os.path import dirname, realpath; sys.path.append(dirname(dirname(realpath(__file__))))

from logger.utils.read_config import read_config
from logger.utils.stderr_logging import DEFAULT_LOGGING_FORMAT
from logger.utils.stderr_logging import setUpStdErrLogging
from logger.utils.stderr_logging import StdErrLoggingHandler
from logger.transforms.to_das_record_transform import ToDASRecordTransform
from logger.writers.text_file_writer import TextFileWriter
from logger.writers.composed_writer import ComposedWriter
from logger.writers.network_writer import NetworkWriter
from server.server_api import ServerAPI
from server.logger_runner import LoggerRunner

# Imports for running CachedDataServer
from logger.readers.composed_reader import ComposedReader
from logger.readers.network_reader import NetworkReader
from logger.transforms.from_json_transform import FromJSONTransform
from logger.utils.cached_data_server import CachedDataServer

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
  def __init__(self, api=None, data_server_websocket=None,
               interval=0.5, max_tries=3, logger_log_level=logging.WARNING):
    """Read desired/current logger configs from Django DB and try to run the
    loggers specified in those configs.

    api - ServerAPI (or subclass) instance by which LoggerManager will get
          its data store updates

    data_server_websocket - websocket address to which we're going to send
          our status updates.

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

    # Data server to which we're going to send status updates
    self.data_server_websocket = data_server_websocket

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
      name='logger_runner',
      target=self.local_logger_runner, daemon=True)
    local_logger_thread.start()

    # Update configs in a separate thread.
    self.update_configs_thread = threading.Thread(
      name='update_configs_loop',
      target=self.update_configs_loop, daemon=True)
    self.update_configs_thread.start()

    # If we've got the address of a data server websocket, start a
    # thread to send our status updates to it.
    if self.data_server_websocket:
      self.send_status_thread = threading.Thread(
        name='send_status_loop',
        target=self._send_status_loop, daemon=True)
      self.send_status_thread.start()

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

      # If configs have changed, send updated ones to the
      # logger_runner and to the data_server.
      if not new_configs == self.old_configs:
        self.logger_runner.set_configs(new_configs)
        #self._send_status()


  ############################
  def _send_status_loop(self):
    """Iteratively grab status messages from the api and send them out as
    JSON to whatever writer we're using to broadcast our logger
    statuses. In theory we could be much more efficient and directly
    grab status updates in _process_logger_runner_messages() when we
    get them from the LoggerRunners.

    Websockets are async, so we need to use an inner function and a
    new event loop to handle the whole async/await thing.
    """

    ############################
    async def _async_send_status_loop(self):
      """Inner async function that actually implements the fetching and
      sending of status messages."""

      # We stash previous_configs so that we know not to send them if
      # they haven't changed since last check. We keep the raw
      # previous_status separately, because we have to do some
      # processing to get it into a form that's useful for our clients,
      # and we want do avoid doing that processing if we can.
      previous_cruise_def = {}
      previous_logger_status = {}

      # If we only have a server port but not a name, use 'localhost'
      ws_name = self.data_server_websocket
      if ws_name.find(':') == 0:
        ws_name = 'localhost' + ws_name

      # Even if things haven't changed, we want to send a full status
      # update every N seconds.
      SEND_EVERY_N_SECONDS = 5
      last_status_sent = 0

      while not self.quit_flag:
        try:
          logging.info('Connecting to websocket: "%s"', ws_name)
          async with websockets.connect('ws://' + ws_name) as ws:
            while not self.quit_flag:
              # Sleep for a bit before going around (also, before we try the
              # first time, to let the LoggerManager start up).
              await asyncio.sleep(self.interval)

              # Assemble information to draw page
              try:
                cruise_def = {
                  'cruise_id': api.get_configuration().id,
                  'loggers': api.get_loggers(),
                  'modes': api.get_modes(),
                  'active_mode': api.get_active_mode()
                }
              except (AttributeError, ValueError):
                logging.info('No cruise definition found')
                cruise_def = {}

              # Has our cruise definition changed? If so, send update
              if not cruise_def == previous_cruise_def:
                # Send cruise metadata
                cruise_message = {
                  'type':'publish',
                  'data':{'timestamp': time.time(),
                          'fields': {'status:cruise_definition': cruise_def}
                  }
                }
                logging.info('sending cruise update: %s', cruise_message)
                await ws.send(json.dumps(cruise_message))
                previous_cruise_def = cruise_def

              # We expect status to be a dict of timestamp:{logger status
              # dict} entries. If we don't have any yet, work with a dummy
              # entry.
              logger_status = self.api.get_status() or {0: {}}

              # Has anything changed with logger statuses? If not, just send
              # a heartbeat.
              logger_status_changed = False
              for timestamp in sorted(logger_status.keys()):
                timestamped_status = logger_status[timestamp]
                if not timestamped_status == previous_logger_status:
                  previous_logger_status = timestamped_status
                  logger_status_changed = True

              # If it's been at least N seconds, force a send of status
              if time.time() > last_status_sent + SEND_EVERY_N_SECONDS:
                logger_status_changed = True
                last_status_sent = time.time()

              if not logger_status_changed:
                logger_status = {}

              status_message = {
                'type':'publish',
                'data':{'timestamp': time.time(),
                        'fields': {'status:logger_status': logger_status}
                }
              }
              logging.debug('sending status update: %s', status_message)
              await ws.send(json.dumps(status_message))

        except BrokenPipeError:
          pass
        except websockets.exceptions.ConnectionClosed:
          logging.warning('Lost websocket connection to data server; '
                          'trying to reconnect.')
          await asyncio.sleep(0.2)
        except OSError as e:
          logging.info('Unable to connect to data server. '
                          'Sleeping to try again...')
          logging.info('Connection error: %s', str(e))
          await asyncio.sleep(5)

    # Now call the async process in its own event loop
    status_event_loop = asyncio.new_event_loop()
    status_event_loop.run_until_complete(_async_send_status_loop(self))
    status_event_loop.close()

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
def run_data_server(data_server_websocket, data_server_udp,
                    data_server_back_seconds, data_server_cleanup_interval,
                    data_server_interval):
  """Run a CachedDataServer (to be called as a separate process),
  accepting websocket connections and listening for UDP broadcasts
  on the specified port to receive data to be cached and served.
  """
  network_readers = [NetworkReader(network=network)
                     for network in data_server_udp.split(',')]
  transform = FromJSONTransform()

  reader = ComposedReader(readers=network_readers, transforms=[transform])
  writer = CachedDataServer(data_server_websocket, data_server_interval)

  # Every N seconds, we're going to detour to clean old data out of cache
  next_cleanup_time = time.time() + data_server_cleanup_interval

  # Loop, reading data and writing it to the cache
  try:
    while True:
      record = reader.read()
      logging.debug('Got record: %s', record)

      # If, for some reason, we get empty record try again
      writer.cache_record(record)

      # Is it time for next cleanup?
      now = time.time()
      if now > next_cleanup_time:
        writer.cleanup(now - data_server_back_seconds)
        next_cleanup_time = now + data_server_cleanup_interval
  except KeyboardInterrupt:
    logging.warning('Received KeyboardInterrupt - shutting down')
    writer.quit()

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

  parser.add_argument('--data_server_websocket', dest='data_server_websocket',
                      action='store', default=':8766',
                      help='Address at which to connect to cached data server '
                      'to send status updates.')

  parser.add_argument('--start_data_server', dest='start_data_server',
                      action='store_true', default=False,
                      help='Whether to start our own cached data server.')
  parser.add_argument('--data_server_udp', dest='data_server_udp',
                      action='store', default=':6225',
                      help='If we are starting our own cached data server, on '
                      'what comma-separated network port(s) it should listen '
                      'for UDP broadcasts, e.g. :6221,:6224.')
  parser.add_argument('--data_server_back_seconds',
                      dest='data_server_back_seconds', action='store',
                      type=float, default=480,
                      help='Maximum number of seconds of old data to keep '
                      'for serving to new clients.')
  parser.add_argument('--data_server_cleanup_interval',
                      dest='data_server_cleanup_interval',
                      action='store', type=float, default=60,
                      help='How often to clean old data out of the cache.')
  parser.add_argument('--data_server_interval', dest='data_server_interval',
                      action='store', type=float, default=1,
                      help='How many seconds to sleep between successive '
                      'sends of data to clients.')

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

  # If we have (or are going to have) a cached data server, set up
  # logging of stderr to it. Use a special format that prepends the
  # log level to the message, to aid in filtering.
  if args.data_server_udp:
    stderr_network_writer = ComposedWriter(
      transforms=ToDASRecordTransform(field_name='stderr:logger_manager'),
      writers=NetworkWriter(network=args.data_server_udp))
    stderr_format = '%(levelno)d\t%(levelname)s\t' + DEFAULT_LOGGING_FORMAT
    logging.getLogger().addHandler(StdErrLoggingHandler(stderr_network_writer,
                                                        stderr_format))

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
  # TODO: decide if we even need this. Disabled for now
  #logging.getLogger().addHandler(WriteToAPILoggingHandler(api))

  ############################
  # Create our LoggerManager
  logger_manager = LoggerManager(
    api=api,
    data_server_websocket=args.data_server_websocket,
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
  # If we're supposed to be running our own CachedDataServer, start it
  # here in its own process.
  if args.start_data_server:
    data_server_proc = multiprocessing.Process(
      target=run_data_server,
      args=(args.data_server_websocket, args.data_server_udp,
            args.data_server_back_seconds, args.data_server_cleanup_interval,
            args.data_server_interval),
      daemon=True)
    data_server_proc.start()

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
