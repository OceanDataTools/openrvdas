#! /usr/bin/env python3
"""
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
import websockets
import yaml

# For communicating with supervisord server
from xmlrpc.client import ServerProxy
from xmlrpc.client import Fault as XmlRpcFault

from collections import OrderedDict

from urllib.parse import unquote
from os.path import dirname, realpath

# Add the openrvdas components onto sys.path
sys.path.append(dirname(dirname(realpath(__file__))))

from logger.utils.read_config import read_config
from logger.transforms.to_das_record_transform import ToDASRecordTransform
from logger.writers.text_file_writer import TextFileWriter
from logger.writers.composed_writer import ComposedWriter
from logger.writers.cached_data_writer import CachedDataWriter
from server.server_api import ServerAPI
from server.logger_runner import LoggerRunner

# Imports for running CachedDataServer
from server.cached_data_server import CachedDataServer
from logger.readers.udp_reader import UDPReader
from logger.transforms.from_json_transform import FromJSONTransform

from logger.utils.stderr_logging import DEFAULT_LOGGING_FORMAT

DEFAULT_MAX_TRIES = 3

SOURCE_NAME = 'LoggerSupervisor'
USER = getpass.getuser()
HOSTNAME = socket.gethostname()

DEFAULT_SUPERVISOR_URL = 'http://localhost:8001'
DEFAULT_SUPERVISOR_CONFIG_FILEPATH = '/opt/openrvdas/server/supervisord/supervisor.d/logger_supervisor.ini'

############################
def kill_handler(self, signum):
  """Translate an external signal (such as we'd get from os.kill) into a
  KeyboardInterrupt, which will signal the start() loop to exit nicely."""
  raise KeyboardInterrupt('Received external kill signal')

################################################################################
################################################################################
class SupervisorConnector:
  ############################
  def __init__(self,  supervisor_url, config_filepath=None):
    """Connect to a supervisord process to manage processes.
    ```
    supervisor_url - URL at which to connect to the supervisord process,
          e.g. http://localhost:8001

    config_filepath - location of config .ini file which should be
          read/written by supervisord.
    ```
    """
    # Open our XMLRPC connection to the supervisord process
    self.supervisor_url = supervisor_url
    self.config_filepath = config_filepath

    # Try to connect. If we fail, sleep a little and try again
    while True:
      self.supervisor_rpc = ServerProxy(supervisor_url + '/RPC2')
      try:
        supervisor_state = self.supervisor_rpc.supervisor.getState()
        if supervisor_state['statename'] == 'RUNNING':
          break

        logging.error('Supervisord is not running. State is "%s"',
                      supervisor_state['statename'])
      except ConnectionRefusedError:
        logging.error('Unable to connect to supervisord at %s', supervisor_url)
      time.sleep(5)
      logging.warning('Retrying connection to %s', supervisor_url)

  ############################
  def clean_name(self, config_name):
    """Remove characters from a string that supervisord can't handle as
    a process name.
    """
    return config_name.replace('/', '+')

  ############################
  def start_configs(self, configs_to_start, group=None):
    """Ask supervisord to start the listed configs. Note that all logger
    configs are part of group 'logger', so we need to prefix all names
    with 'logger:' when talking to supervisord about them.

    configs_to_start - a list of config names that should be started.

    group - process group in which the configs were defined; will be
        prepended to config names.
    """
    configs = list(configs_to_start)  # so we can order results
    config_calls = []
    
    for config in configs:
      config = self.clean_name(config)  # get rid of objectionable characters
      if group:
        config = group + ':' + config
      config_calls.append({'methodName':'supervisor.startProcess',
                           'params':[config, False]})

    results = self.supervisor_rpc.system.multicall(config_calls)
    # Let's see what the results are
    for i in range(len(results)):
      result = results[i]
      config = configs[i]
      if type(result) is dict:
        if result['faultCode'] == 60:
          logging.warning('Starting process %s, but already started', config)
        else:
          logging.warning('Starting process %s: %s', config,
                          result['faultString'])

  ############################
  def start_group(self, group):
    """Ask supervisord to start the listed process config group.

    group - name of process group to start.
    """
    self.supervisor_rpc.supervisor.startProcessGroup(group)

  ############################
  def stop_configs(self, configs_to_stop, group=None):
    """Ask supervisord to stop the listed configs. Note that all logger
    configs are part of group 'logger', so we need to prefix all names
    with 'logger:' when talking to supervisord about them.

    configs_to_stop - a list of config names that should be stopped.

    group - process group in which the configs were defined; will be
        prepended to config names.
    """
    configs = list(configs_to_stop)  # so we can order results
    config_calls = []
    
    for config in configs:
      config = self.clean_name(config)  # get rid of objectionable characters
      if group:
        config = group + ':' + config
      config_calls.append({'methodName':'supervisor.stopProcess',
                           'params':[config, False]})

    results = self.supervisor_rpc.system.multicall(config_calls)
    # Let's see what the results are
    for i in range(len(results)):
      result = results[i]
      config = configs[i]
      if type(result) is dict:
        if result['faultCode'] == 60:
          logging.warning('Stopping process %s, but already stopped', config)
        else:
          logging.warning('Stopping process %s: %s', config,
                          result['faultString'])

  ############################
  def create_new_supervisor_file(self, configs, group=None,
                                 config_filepath=None,
                                 user=None, base_dir=None, max_tries=3):
    """Create a new configuration file for supervisord to read.

    configs - a dict of {logger_name:{config_name:config_spec}} entries.

    group - process group in which the configs will be defined; will be
        prepended to config names.

    config_filepath - where the file should be written. If omitted, will
        use the value passed in when the SupervisorConnector was created.

    user - user name under which processes should run. Will default to
        current user.

    base_dir - directory from which executables should be called.

    max_tries - number of times a process should be tried before
        giving it up as failed.
    """
    # Fill in some defaults if they weren't provided
    config_filepath = config_filepath or self.config_filepath
    user = user or getpass.getuser()
    base_dir = base_dir or dirname(dirname(realpath(__file__)))

    # We'll build the string for the supervisord config file in 'config_str'
    config_str = '\n'.join([
      '; DO NOT EDIT UNLESS YOU KNOW WHAT YOU\'RE DOING. This configuration ',
      '; file was produced automatically by the logger_supervisor.py script',
      '; and will be overwritten by it as well.',
      '', ''
      ])

    config_names = []
    for logger, logger_configs in configs.items():
      for config_name, config in logger_configs.items():
        # Supervisord doesn't like '/' in program names
        config_name = self.clean_name(config_name)
        config_names.append(config_name)
        config_json = json.dumps(config)

        # Use fancy new f-strings for formatting
        config_str += '\n'.join([
          f'[program:{config_name}]',
          f'command=/usr/local/bin/python3 logger/listener/listen.py --config_string \'{config_json}\' -v',
          f'directory={base_dir}',
          f'autostart=false',
          f'autorestart=true',
          f'startretries={max_tries}',
          f'stderr_logfile=/var/log/openrvdas/{logger}.err.log',
          f'stdout_logfile=/var/log/openrvdas/{logger}.out.log',
          f'user={user}',
          '', '',
        ])

    # If we've been given a group name, group all the logger configs
    # together under it so we can start them all at the same time with
    # a single call.
    if group:
      config_str += '\n'.join([
        '[group:%s]' % group,
        'programs=%s' % ','.join(config_names),
        ''
      ])

    # Open and write the config file.
    with open(config_filepath, 'w') as config_file:
      config_file.write(config_str)

    # Force supervisord to reload the logger group, which should get
    # it to recognize the new file.
    if group:
      self.update_group(group)

  ############################
  def update_group(self, group):
    """Ask supervisord to re-read the config file and start/stop relevant
    processes/configs as specified in it.
    """
    self.supervisor_rpc.supervisor.reloadConfig()
    try:
      self.supervisor_rpc.supervisor.removeProcessGroup(group)
    except XmlRpcFault:
      pass
    try:
      self.supervisor_rpc.supervisor.addProcessGroup(group)
    except XmlRpcFault:
      pass

################################################################################
################################################################################
class LoggerSupervisor:
  ############################
  def __init__(self,  supervisor_url, supervisor_config_filepath,
               api=None, data_server_websocket=None,
               interval=0.5, max_tries=3, logger_log_level=logging.WARNING):
    """Read desired/current logger configs from Django DB and try to run the
    loggers specified in those configs.
    ```
    supervisor_url - URL at which to connect to the supervisord process,
          e.g. http://localhost:8001

    supervisor_config_filepath - Location of file where supervisord will
          look for process definitions

    api - ServerAPI (or subclass) instance by which LoggerManager will get
          its data store updates

    data_server_websocket - websocket address to which we are going to send
          our status updates.

    interval - number of seconds to sleep between checking/updating loggers

    max_tries - number of times to try a failed server before giving up

    logger_log_level - At what logging level our component loggers
          should operate.
    ```
    """
    # Set signal to catch SIGTERM and convert it into a
    # KeyboardInterrupt so we can shut things down gracefully.
    try:
      signal.signal(signal.SIGTERM, kill_handler)
    except ValueError:
      logging.warning('LoggerSupervisor not running in main thread; '
                      'shutting down with Ctl-C may not work.')

    # Set up XMLRPC connection to supervisord
    self.supervisor = SupervisorConnector(supervisor_url=supervisor_url)

    # Where we expect supervisord to look for config process file.
    self.supervisor_config_filepath = supervisor_config_filepath

    # api class must be subclass of ServerAPI
    if not issubclass(type(api), ServerAPI):
      raise ValueError('Passed api "%s" must be subclass of ServerAPI' % api)
    self.api = api
    self.interval = interval
    self.max_tries = max_tries
    self.logger_log_level = logger_log_level
    self.quit_flag = False

    # Where we store the latest status/error reports.
    self.status = {}
    self.errors = {}

    # We'll loop to check the API for updates to our desired
    # configs. Do this in a separate thread. Also keep track of
    # currently active configs so that we know when an update is
    # actually needed.
    self.update_configs_thread = None
    self.config_lock = threading.Lock()
    self.loggers = {}                 # dict of all loggers and their configs
    self.active_configs = set()       # which of those configs are active now?

    # Fetch the complete set of loggers and configs from API; store
    # them in self.loggers and create a .ini file for supervisord to
    # run them.
    self._build_new_config_file()

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
    """Start the threads that make up the LoggerSupervisor operation:

    1. Configuration update loop
    2. Loop to read logger stderr/status and either output it or
       transmit it to a cached data server

    Start threads as daemons so that they'll automatically terminate
    if the main thread does.
    """
    # Update configs in a separate thread.
    self.update_configs_thread = threading.Thread(
      name='update_configs_loop',
      target=self._update_configs_loop, daemon=True)
    self.update_configs_thread.start()

    # If we've got the address of a data server websocket, start a
    # thread to send our status updates to it.
    self.read_logger_status_thread = threading.Thread(
        name='read_logger_status_loop',
        target=self._read_logger_status_loop, daemon=True)
    self.read_logger_status_thread.start()

  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True

  ############################
  def _build_new_config_file(self):
    """Fetch latest dict of configs from API. Update self.loggers to
    reflect them and build a .ini file to run them.
    """
    # Inefficient: first fetch loggers, then one by one grab their
    # configs.
    loggers = self.api.get_loggers()
    self.loggers = {}
    for logger, configs in loggers.items():
      config_names = configs.get('configs', [])
      logger_configs = {config_name:api.get_logger_config(config_name)
                        for config_name in config_names}
      self.loggers[logger] = logger_configs

    # Now create a .ini file of those configs for supervisord to run.
    with self.config_lock:
      config_filepath = self.supervisor_config_filepath
      logging.warning('Creating new configs in %s.', config_filepath)
      self.supervisor.create_new_supervisor_file(
        configs=self.loggers,
        config_filepath=config_filepath,
        group='logger')
      logging.warning('Done creating new configs - reloading.')
      self.supervisor.update_group('logger')

    # Finally, reset the currently active configurations
    self._update_configs()

  ############################
  def _update_configs_loop(self):
    """Iteratively check the API for updated configs and send them to the
    appropriate LoggerRunners.
    """
    while not self.quit_flag:
      self._update_configs()
      time.sleep(self.interval)

  ############################
  def _update_configs(self):
    """Get list of new (latest) configs. If any have changed,

    1. Shut down any configs that aren't a part of new active configs.
    2. Start and newly-active configs.
    """
    with self.config_lock:
      try:
        # Get new configs in dict {logger:{'configs':[config_name,...]}}
        new_logger_configs = self.api.get_logger_configs()
        new_configs = set([new_logger_configs[logger].get('name', None)
                           for logger in new_logger_configs])
      except (AttributeError, ValueError):
        return

      # If configs have changed, start new ones and stop old ones.
      if new_configs == self.active_configs:
        return

      configs_to_start = new_configs - self.active_configs
      configs_to_stop = self.active_configs - new_configs

      if configs_to_stop:
        logging.warning('Stopping configs: %s', configs_to_stop)
        self.supervisor.stop_configs(configs_to_stop, group='logger')
        logging.warning('We should read final output from these configs!')

      if configs_to_start:
        logging.warning('Starting new configs: %s', configs_to_start)
        self.supervisor.start_configs(configs_to_start, group='logger')

      # Cache our new configs for the next time around
      self.active_configs = new_configs

  ############################
  async def _publish_to_data_server(self, ws, data):
    """Encode and publish a dict of values to the cached data server.
    """
    message = json.dumps({'type': 'publish', 'data': data})
    await ws.send(message)
    try:
      result = await ws.recv()
      response = json.loads(result)
      if type(response) is dict and response.get('status', None) == 200:
        return
      logging.warning('Got bad response from data server: %s', result)
    except json.JSONDecodeError:
      logging.warning('Got unparseable response to "publish" message '
                      'to data server: %s', result)

  ############################
  def _read_logger_status_loop(self):
    """Iteratively grab messages to send to cached data server and send
    them off via websocket.

    Websockets are async, so we need to use an inner function and a
    new event loop to handle the whole async/await thing.
    """

    ############################
    async def _async_send_to_data_server_loop(self):
      """Inner async function that actually implements the fetching and
      sending of status messages."""

      logging.warning('!!!CHECK IF DATA_SERVER IS DEFINED!')
      logging.warning('_async_send_to_data_server_loop sleeping a long time')
      await asyncio.sleep(1000000)

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
             logging.info('Connected to websocket: "%s"', ws_name)
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
                await self._publish_to_data_server(ws, next_message)
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
                cruise_data = {
                  'timestamp': time.time(),
                  'fields': {'status:cruise_definition': cruise_def}
                }
                logging.debug('sending cruise update: %s', cruise_data)
                await self._publish_to_data_server(ws, cruise_data)

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

              status_data = {
                'timestamp': now,
                'fields': {'status:logger_status': logger_status}
              }
              logging.debug('sending status update: %s', status_data)
              await self._publish_to_data_server(ws, status_data)

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
          error_message = {'fields':{'stderr:logger:'+logger: error_tuples}}
          with self.data_server_lock:
            self.data_server_queue.put(error_message)

    # If there were any errors not associated with a specific logger,
    # send those as general logger_manager errors.
    if self.errors:
      logging.error('Errors from LoggerRunner: %s', self.errors)
      error_tuples = [(now, error) for error in self.errors]
      error_message = {'fields':{'stderr:logger_manager': error_tuples}}
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

  parser.add_argument('--supervisor_url', dest='supervisor_url',
                      action='store', default=DEFAULT_SUPERVISOR_URL,
                      help='Address at which to connect to supervisord '
                      'http server.')

  parser.add_argument('--supervisor_config_filepath',
                      dest='supervisor_config_filepath', action='store',
                      default=DEFAULT_SUPERVISOR_CONFIG_FILEPATH,
                      help='Location of file where supervisord will look '
                      'for process definitions.')

  parser.add_argument('--data_server_websocket', dest='data_server_websocket',
                      action='store', default=None,
                      help='Address at which to connect to cached data server '
                      'to send status updates.')

  parser.add_argument('--start_data_server', dest='start_data_server',
                      action='store_true', default=False,
                      help='Whether to start our own cached data server.')
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

  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  parser.add_argument('-V', '--logger_verbosity', dest='logger_verbosity',
                      default=0, action='count',
                      help='Increase output verbosity of component loggers')
  args = parser.parse_args()

  # Set up logging first of all
  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

  log_level = LOG_LEVELS[min(args.verbosity, max(LOG_LEVELS))]
  logging.basicConfig(format=LOGGING_FORMAT)

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
  # Create our LoggerSupervisor
  logger_supervisor = LoggerSupervisor(
    supervisor_url=args.supervisor_url,
    supervisor_config_filepath=args.supervisor_config_filepath,
    api=api,
    data_server_websocket=args.data_server_websocket,
    interval=args.interval,
    max_tries=args.max_tries,
    logger_log_level=logger_log_level)

  # Register a callback: when api.set_active_mode() or api.set_config()
  # have completed, they call api.signal_update(). We're registering
  # update_configs() with the API so that it gets called when the api
  # signals that an update has occurred.

  # When an active config changes in the database, update our configs here
  api.on_update(callback=logger_supervisor._update_configs)

  # When new configs are loaded, update our file of config processes
  api.on_load(callback=logger_supervisor._build_new_config_file)

  # When told to quit, shut down gracefully
  api.on_quit(callback=logger_supervisor.quit)

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
  logger_supervisor.start()

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
      if logger_supervisor.update_configs_thread:
        logger_supervisor.update_configs_thread.join()
      else:
        logging.warning('LoggerManager has no update_configs_thread? '
                        'Exiting...')

    else:
      # Create reader to read/process commands from stdin. Note: this
      # needs to be in main thread for Ctl-C termination to be properly
     # caught and processed, otherwise interrupts go to the wrong places.

      # Set up command line interface to get commands. Start by
      # reading history file, if one exists, to get past commands.
      hist_filename = '.openrvdas_logger_supervisor_history'
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
  logging.debug('Done with logger_supervisor.py - exiting')
