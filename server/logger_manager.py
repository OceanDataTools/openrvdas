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
     Modes for NBP1406: off, port, underway

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
from logger.writers.cached_data_writer import CachedDataWriter
from server.server_api import ServerAPI
from server.logger_runner import LoggerRunner

# Imports for running CachedDataServer
from logger.utils.cached_data_server import CachedDataServer
from logger.readers.udp_reader import UDPReader
from logger.transforms.from_json_transform import FromJSONTransform

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

############################
def parse_udp_spec(spec):
  """Format should be [[interface:]destination:]port"""
  destination = interface = ''
  addr = spec.split(':')
  try:
    port = int(addr[-1])    # port is last arg
  except ValueError:
    raise ValueError('UDP spec "%s" has non-integer port: "%s"; should be '
                     'format "[[interface:]destination:]port"', spec, port)
  if len(addr) > 1:
    destination = addr[-2]  # destination (multi/broadcast) is prev arg
  if len(addr) > 2:
    interface = addr[-3]    # interface is first arg
  if len(addr) > 3:
    raise ValueError('Improper UDP specification: "%s"; should be format '
                     '"[[interface:]destination:]port"', spec)
  return (interface, destination, port)

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

    self.quit_flag = False

    # Where we store the latest status/error reports we've gotten from
    # the LoggerRunner
    self.status = {}
    self.errors = {}
    
    # We'll loop to check the API for updates to our desired
    # configs. Do this in a separate thread. Also keep track of
    # old/current configs so that we know when an update is actually
    # needed.
    self.update_configs_thread = None
    self.old_configs = {}
    self.config_lock = threading.Lock()

    # If we have a cached data server (either one we've started, or
    # one we're just connecting to, we'll use a separate thread to
    # send it status updates. We'll pop updates into the
    # data_server_queue to get them sent by the thread.
    self.send_to_data_server_thread = None
    self.data_server_queue = queue.Queue()
    self.data_server_lock = threading.Lock()

    # Data server to which we're going to send status updates
    self.data_server_websocket = data_server_websocket


    # Grab event loop so everyone who wants can make sure they're
    # using the same one.
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
      name='logger_runner', target=self.local_logger_runner, daemon=True)
    local_logger_thread.start()

    # Update configs in a separate thread.
    self.update_configs_thread = threading.Thread(
      name='update_configs_loop',
      target=self.update_configs_loop, daemon=True)
    self.update_configs_thread.start()

    # If we've got the address of a data server websocket, start a
    # thread to send our status updates to it.
    if self.data_server_websocket:
      self.send_to_data_server_thread = threading.Thread(
        name='send_to_data_server_loop',
        target=self._send_to_data_server_loop, daemon=True)
      self.send_to_data_server_thread.start()

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
      status = self.logger_runner.check_loggers(manage=True)
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
  def _send_to_data_server_loop(self):
    """Iteratively grab messages to send to cached data server and send
    them off via websocket.

    Websockets are async, so we need to use an inner function and a
    new event loop to handle the whole async/await thing.
    """

    ############################
    async def _async_send_to_data_server_loop(self):
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
      if not ':' in ws_name and int(ws_name) > 0:  # if gave us just port
        ws_name = 'localhost:' + ws_name
      if ws_name.find(':') == 0:  # if gave us :port
        ws_name = 'localhost' + ws_name

      # Even if things haven't changed, we want to send a full status
      # update every N seconds.
      SEND_CRUISE_EVERY_N_SECONDS = 10
      SEND_STATUS_EVERY_N_SECONDS = 5
      last_cruise_def_sent = 0
      last_status_sent = 0

      while not self.quit_flag:
        try:
          logging.info('Connecting to websocket: "%s"', ws_name)
          async with websockets.connect('ws://' + ws_name) as ws:
            while not self.quit_flag:

              # Work through the messages in the queue, sending the
              # ones we already have before doing anything else.
              next_message = None
              with self.data_server_lock:
                if not self.data_server_queue.empty():
                  next_message = self.data_server_queue.get()

              # If there's something to send, send it and immediately
              # loop back to see if there's more to send
              if next_message:
                await ws.send(json.dumps(next_message))
                continue;

              # If we're here, we've caught up on sending stuff that's
              # in the send queue. Check if anything has changed
              # behind our back in the database.

              now = time.time()

              # Assemble information from DB about what loggers should
              # exist and what states they *should* be in. We'll send
              # this to the cached data server whenever it changes (or
              # if it's been a while since we have).
              #
              # Looks like:
              # {'active_mode': 'log',
              #  'cruise_id': 'NBP1406',
              #  'loggers': {'PCOD': {'active': 'PCOD->file/net',
              #                       'configs': ['PCOD->off',
              #                                   'PCOD->net',
              #                                   'PCOD->file/net',
              #                                   'PCOD->file/net/db']},
              #               next_logger: next_configs,
              #               ...
              #             },
              #  'modes': ['off', 'monitor', 'log', 'log+db']
              # }
              try:
                cruise = api.get_configuration() # a Cruise object
                cruise_def = {
                  'cruise_id': cruise.id,
                  'loggers': api.get_loggers(),
                  'modes': cruise.modes(),
                  'active_mode': cruise.current_mode.name
                }
              except (AttributeError, ValueError):
                logging.debug('No cruise definition found')
                cruise_def = {}

              # Has our cruise definition changed, or has it been a
              # while since we've sent it? If so, send update.
              if not cruise_def == previous_cruise_def or \
                 now - last_cruise_def_sent > SEND_CRUISE_EVERY_N_SECONDS:
                cruise_message = {
                  'type':'publish',
                  'data':{'timestamp': time.time(),
                          'fields': {'status:cruise_definition': cruise_def}
                  }
                 }
                logging.debug('sending cruise update: %s', cruise_message)
                await ws.send(json.dumps(cruise_message))
                previous_cruise_def = cruise_def
                last_cruise_def_sent = now

              # Check our previously-sent logger status against the
              # most-recently received one from the LoggerRunner. Has
              # it changed? If so, send an update. Also send update if
              # it's been a while since we've sent one.
              logger_status = self.status

              # Has anything changed with logger statuses? If so, we'll
              # send a full update. Otherwise we'll just send a heartbeat
              status_changed = not logger_status == previous_logger_status

              # If it's been too long since we last sent an update,
              # pretend status has changed so we'll send a new one
              # just to keep up.
              if now - last_status_sent > SEND_STATUS_EVERY_N_SECONDS:
                status_changed = True
                logging.debug('sending full status; time diff: %s',
                              now - last_status_sent)
                
              if status_changed:
                previous_logger_status = logger_status
                last_status_sent = now
                logging.debug('sending full status')
              else:
                logger_status = {}
                logging.debug('sending heartbeat')
                
              status_message = {
                'type':'publish',
                'data':{'timestamp': now,
                        'fields': {'status:logger_status': logger_status}
                }
              }
              logging.debug('sending status update: %s', status_message)
              await ws.send(json.dumps(status_message))

              # Send queue is (or was recently) empty, and we've sent
              # a status update. Snooze a bit before looping to check
              # again.
              await asyncio.sleep(self.interval)

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
    status_event_loop.run_until_complete(_async_send_to_data_server_loop(self))
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
    self.status = message.get('status', None)
    self.errors = message.get('errors', None)
    now = time.time()
    if self.status:
      self.api.update_status(self.status)
      # For each logger, publish any errors to the stderr for that
      # logger. Aggregate them into a single message of [(timestamp,
      # error), ...] for efficiency, but we fudge the timestamp as
      # "now" rather than parsing it off of the error message
      # itself. We may need to fix that.
      for logger in self.status:
        logger_status = self.status.get(logger)
        logger_errors = logger_status.get('errors', [])
        if logger_errors:
          error_tuples = [(now, error) for error in logger_errors]
          error_message = {
            'type':'publish',
            'data':{'fields':{'stderr:logger:'+logger: error_tuples}}
           }
          with self.data_server_lock:
            self.data_server_queue.put(error_message)

    # If there were any errors not associated with a specific logger,
    # send those as general logger_manager errors.
    if self.errors:
      logging.error('Errors from LoggerRunner: %s', self.errors)
      error_tuples = [(now, error) for error in self.errors]
      error_message = {
        'type':'publish',
        'data':{'fields':{'stderr:logger_manager': error_tuples}}
      }
      with self.data_server_lock:
        self.data_server_queue.put(error_message)

################################################################################
def run_data_server(data_server_websocket, data_server_udp,
                    data_server_back_seconds, data_server_cleanup_interval,
                    data_server_interval):
  """Run a CachedDataServer (to be called as a separate process),
  accepting websocket connections and listening for UDP broadcasts
  on the specified port to receive data to be cached and served.
  """
  # First get the port that we're going to run the data server on. Because
  # we're running it locally, it should only have a port, not a hostname.
  # We should try to handle it if they prefix with a ':', though.
  websocket_port = int(data_server_websocket.split(':')[-1])
  server = CachedDataServer(port=websocket_port, interval=data_server_interval)

  # If we have a data_server_udp specified, start up a reader that
  # will listen on that UDP port and cache what it receives.
  if data_server_udp:
    group_port = data_server_udp.split(':')
    port = int(group_port[-1])
    multicast_group = group_port[-2] if len(group_port) == 2 else ''
    reader = UDPReader(port=port, source=multicast_group)
    transform = FromJSONTransform()

  # Every N seconds, we're going to detour to clean old data out of cache
  next_cleanup_time = time.time() + data_server_cleanup_interval

  # Loop, reading data and writing it to the cache
  try:
    while True:
      # If we have a reader, try reading from it
      if data_server_udp:
        try:
          record = reader.read()
          if record:
            server.cache_record(transform.transform(record))
        except ValueError as e:
          logging.warning(
            'Data Server UDP port received non-JSON message: %s', str(e))
          continue

      # If no reader, sleep until it's time to do another cleanup
      else:
        time.sleep(data_server_cleanup_interval)

      # Is it time for next cleanup?
      now = time.time()
      if now > next_cleanup_time:
        server.cleanup(oldest=now - data_server_back_seconds)
        next_cleanup_time = now + data_server_cleanup_interval
  except KeyboardInterrupt:
    logging.warning('Received KeyboardInterrupt - shutting down')
    server.quit()

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
                      action='store', default='8766',
                      help='Address at which to connect to cached data server '
                      'to send status updates.')

  parser.add_argument('--start_data_server', dest='start_data_server',
                      action='store_true', default=False,
                      help='Whether to start our own cached data server.')
  parser.add_argument('--data_server_udp', dest='data_server_udp',
                      action='store', default='6225',
                      help='If we are starting our own cached data server, on '
                      'what comma-separated network port(s) it should listen '
                      'for UDP broadcasts, e.g. 6225,6227. For multicast, '
                      'prefix with colon-separated group, e.g. '
                      '224.1.1.1:6225')
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
  if args.data_server_websocket:
    # Format should be [[interface:]destination:]port
    (interface, destination, port) = parse_udp_spec(args.data_server_udp)
    stderr_network_writer = ComposedWriter(
      transforms=ToDASRecordTransform(field_name='stderr:logger_manager'),
      writers=CachedDataWriter(data_server=args.data_server_websocket))
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
