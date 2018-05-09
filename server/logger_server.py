#!/usr/bin/env python3
"""LoggerServers get their desired state of the world via a ServerAPI
instance and attempt to start/stop loggers with the desired configs
by dispatching requests to a local LoggerRunner.

To run the LoggerServer from the command line with (using the default
of an InMemoryServerAPI):

  serverserver/logger_server.py

If an initial cruise config is specified on the command line, as
below:

  server/logger_server.py --config test/configs/sample_cruise.json

the cruise configuration will be loaded and set to its default
mode. If a --mode argument is included, it will be used in place of
the default mode.

If the LoggerServer is created with a websocket specification
(host:port), it will accept connections from LoggerManagers. It
expects the LoggerManagers to identify themselves with a host_id, and
will dispatch any configs listing that host_id to the appropriate
LoggerManager. Configs that have no host_id specified will continue to
be dispatched to the local LoggerRunner; configs specifying a host_id
that doesn't match any connected LoggerManager will not be run:

  server/logger_server.py --websocket localhost:8765

A LoggerManager that would connect to the above LoggerServer could be
launched via:

  server/logger_manager.py --websocket localhost:8765 \
      --host_id knud.host

The -v flag may be specified on any of the above command lines to
increase diagnostic verbosity to "INFO". Repeating the flag sets
verbosity to "DEBUG".

#######################################################
To try out the scripts, open four(!) terminal windows.

1. In the first one, run a listener that monitors UDP port 6224. The
   sample cruise config file defines loggers that write to this port
   when active, so this will be where we see output show up when
   loggers are running:

   logger/listener/listen.py --network :6224 --write_file -

2. In the second one, run the script that sets up the simulate serial
   ports that the sample cruise configuration (in
   tests/configs/sample_cruise.json):

   logger/utils/simulate_serial.py --config test/serial_sim.json -v

3. In the third one, start a LoggerServer with a websocket server:

   server/logger_server.py --config test/configs/sample_cruise.json \
         --websocket localhost:8765 -v

4. In the fourth one, start a LoggerManager that will try to connect
   to the websocket on the LoggerServer you've started.

   server/logger_manager.py --websocket localhost:8765 \
         --host_id knud.host -v

   Note that this LoggerManager is identifying its host as
   "knud.host"; if you look at sample_cruise.json, you'll notice that
   the configs for the "knud" logger have a host restriction of
   "knud.host", meaning that our LoggerServer should try to dispatch
   those configs to this LoggerManager.

5. In the terminal running the LoggerServer, try a few commands:

   command? cruises
   Loaded cruises: NBP1700
   command? modes NBP1700
   Modes for NBP1700: off, port, underway
   command? set_mode NBP1700 port
   ...
   command? set_mode NBP1700 underway
   ...
   command? set_mode NBP1700 off

   When setting the mode to port, you should notice data appearing in
   the listener window, and should see diagnostic output in the
   LoggerServer window.

   When setting the mode to underway, you should see more data
   appearing in the listener window (due to more logger configs
   running), and should see the LoggerManager leap into action as the
   LoggerServer dispatches the configs for "knud.host" to it.

"""
import asyncio
import json
import logging
import os
import queue
import sys
import threading
import time

sys.path.append('.')

from logger.utils.read_json import read_json, parse_json

from server.server_api import ServerAPI

from server.logger_runner import LoggerRunner, run_logging
from server.logger_manager import LoggerManager

from server.websocket_server import WebsocketServer

# Number of times we'll try a failing logger before giving up
DEFAULT_MAX_TRIES = 3

# To keep logger/config names unique, we'll prepend cruise_id,
# separating them by CRUISE_ID_SEPARATOR; e.g. NBP1700:knud
CRUISE_ID_SEPARATOR = ':'

################################################################################
class LoggerServer:
  ############################
  def __init__(self, api=None, websocket=None, interval=0.5, max_tries=3,
               verbosity=0, logger_verbosity=0):
    """Read desired/current logger configs from Django DB and try to run the
    loggers specified in those configs.

    api - ServerAPI (or subclass) instance by which LoggerServer will get
          its data store updates

    websocket - optional host:port on which to open a websocket server
          for LoggerManagers to connect to for dispatches of logger
          configs they should run.

    interval - number of seconds to sleep between checking/updating loggers

    max_tries - number of times to try a failed server before giving up
    """
    # Set up logging levels for both ourselves and for the loggers we
    # start running. Attach a Handler that will write log messages to
    # Django database.
    logging.basicConfig(format=LOGGING_FORMAT)

    log_verbosity = LOG_LEVELS[min(verbosity, max(LOG_LEVELS))]
    log_logger_verbosity = LOG_LEVELS[min(logger_verbosity, max(LOG_LEVELS))]
    run_logging.setLevel(log_verbosity)
    logging.getLogger().setLevel(log_logger_verbosity)

    # api class must be subclass of ServerAPI
    if not issubclass(type(api), ServerAPI):
      raise ValueError('Passed api "%s" must be subclass of ServerAPI' % api)
    self.api = api
    self.interval = interval
    self.max_tries = max_tries
    self.quit_flag = False
    self.websocket_server = None

    # Keep track of old configs so we only send updates to the
    # LoggerManagers when things change.
    self.old_configs = {}
    self.config_lock = threading.Lock()
    
    # Create our own LoggerRunner to use by default when configs don't
    # specify a host restriction. (NOTE: we really ought to find a way
    # to load balance and not take on all unrestricted configs
    # ourselves.)
    self.logger_runner = LoggerRunner(interval=self.interval,
                                      max_tries=self.max_tries)

    # Websocket server where other LoggerManagers can connect. If
    # we're not taking websocket clients, we're done.
    if not websocket:
      return

    # If here, we've been given a host:port for a websocket
    # server. Do the setup we need create the server.
    self.websocket_map = {}  # client_id->websocket
    self.send_queue = {}     # client_id->queue for messages to send to ws
    self.receive_queue = {}  # client_id->queue for messages from ws
    self.websocket_host_map = {}
    self.websocket_client_map = {}

    # A lock to make sure only one thread is messing with the above
    # maps at any given time.
    self.websocket_map_lock = threading.Lock()

    try:
      host, port_str = args.websocket.split(':')
      port = int(port_str)
      self.websocket_server = WebsocketServer(
        host=host, port=port,
        consumer=self.queued_consumer,
        producer=self.queued_producer,
        on_connect=self.register_websocket_client,
        on_disconnect=self.unregister_websocket_client)
      #self.websocket_server.run()

    except ValueError as e:
      logging.error('--websocket arg "%s" not in host:port format',
                    args.websocket)
      exit(1)

  ##########################
  # This is a consumer - it takes a message and does something with it
  async def queued_consumer(self, message, client_id):
   logging.debug('Received message from client #%d: %s', client_id, message)
   self.receive_queue[client_id].put(message)
    
  ############################
  # This is a producer - it produces a message (from the queue) to send
  async def queued_producer(self, client_id):
    while True:
      try:
        message = self.send_queue[client_id].get_nowait()
        if message.strip():
          logging.debug('Sending message to client #%d: %s', client_id, message)
          return message
      except queue.Empty:
        await asyncio.sleep(0.1)

  ############################
  def _set_host_configs(self, host_id, configs):
    """Assign the passed configs to the named host_id."""
    if not self.websocket_server:
      logging.warning('No websocket server - unable to dispatch '
                      'tasks for host_id "%s"', host_id)
      return
    
    client_id = self.websocket_host_map.get(host_id, None)
    if client_id is None:
      logging.error('No host %s available for dispatched tasks', host_id)
      return

    # If here, we're ready to dispatch
    logging.warning('Dispatching configs for host %s', host_id)
    command = 'set_configs ' + json.dumps(configs)
    self.send_queue[client_id].put(command)

  ############################
  def dispatch_configs(self, config_map):
    """We're passed a dict mapping host_ids (or None) to sets of configs.
    Dispatch the configs for None to our local LoggerRunner and see if
    we have the desired hosts for the other configs attached. If so,
    dispatch them, too."""
    # Prior to doing any dispatch, check whether there are any new
    # clients that we haven't properly registered yet.
    if self.websocket_server:
      for client_id, websocket in self.websocket_server.clients().items():
        if not client_id in self.websocket_client_map:
          self.register_websocket_client(websocket, client_id)

    with self.config_lock:
      # The configs indexed under None have no host restrictions. Run
      # them locally (yeah, we should probably distribute these among
      # available hosts for load balancing).
      desired_hosts = config_map.keys()

      # If there are hosts for which we don't have desired configs, it
      # means they shouldn't be running anything; tell them to shut
      # down whatever configs they're running.
      if self.websocket_server:
        for client_id in self.websocket_server.clients():
          host_id = self.websocket_client_map.get(client_id, None)
          if host_id and not host_id in desired_hosts:
            self._set_host_configs(host_id, {})

      # Similarly, we index configs without host restrictions under
      # 'None'; these will be run (for now) with our local
      # LoggerRunner. If there aren't any such configs, tell our
      # LoggerRunner to stop running whatever it's running.
      if not None in desired_hosts:
        self.logger_runner.set_configs({})

      # Now dispatch to the hosts that we *do* want stuff to be
      # running on.
      for host_id, configs in config_map.items():
        # host_id == None indicates configs with no host restriction;
        # we run these locally
        if host_id is None:
          self.logger_runner.set_configs(configs)
        else:
          self._set_host_configs(host_id, configs)

  ############################
  def register_websocket_client(self, websocket, client_id):
    """We've been alerted that a websocket client has connected.
    Register it properly."""
    with self.websocket_map_lock:
      # If we haven't created queues for it yet, do that now
      if not client_id in self.websocket_map:
        self.websocket_map[client_id] = websocket
        self.send_queue[client_id] = queue.Queue()
        self.receive_queue[client_id] = queue.Queue()
      try:
        # We expect initial message to be a host_id declaration
        message_str = self.receive_queue[client_id].get_nowait()
        logging.warning('Websocket client #%d registered as "%s"',
                        client_id, message_str)
        message = parse_json(message_str)
        host_id = message.get('host_id', None)
        self.websocket_host_map[host_id] = client_id
        self.websocket_client_map[client_id] = host_id
      except queue.Empty:
        logging.warning('New client #%d hasn\'t sent id yet', client_id)

  ############################
  def unregister_websocket_client(self, client_id):
    """We've been alerted that a websocket client has disconnected.
    Unegister it properly."""
    with self.websocket_map_lock:
      if client_id in self.websocket_map: del self.websocket_map[client_id]
      if client_id in self.send_queue: del self.send_queue[client_id]
      if client_id in self.receive_queue: del self.receive_queue[client_id]
      
      if client_id in self.websocket_client_map:
        host_id = self.websocket_client_map[client_id]
        del self.websocket_host_map[host_id]
        del self.websocket_client_map[client_id]
      logging.warning('Websocket client #%d has disconnected', client_id)

  ############################
  def update_configs(self, cruise_id=None):
    """Check the API for updated configs for cruise_id, and send them to
    the appropriate LoggerManager. If cruise_id is None, check for all
    cruises."""
    # Get latest configs.
    with self.config_lock:
      if cruise_id:
        new_configs = {cruise_id: api.get_configs(cruise_id) }
      else:
        new_configs = {cruise_id: api.get_configs(cruise_id)
                       for cruise_id in self.api.get_cruises()}

      # If configs haven't changed, we're done - go home.
      if new_configs == self.old_configs:
        return
      self.old_configs = new_configs

    # Sort our configurations for dispatch. 
    config_map = {}
    for cruise_id, cruise_configs in new_configs.items():
      for logger, config in cruise_configs.items():
        
        # If there is a host restriction, set up a dict for configs
        # restricted to that host. If no restriction, file config
        # under key 'None' to run locally.
        logging.debug('Config for logger %s, cruise %s: %s',
                        logger, cruise_id, config)
        if not config:
          continue
        host_id = config.get('host_id', None)
        if not host_id in config_map:
          config_map[host_id] = {}
        cruise_and_logger = cruise_id + CRUISE_ID_SEPARATOR + logger
        config_map[host_id][cruise_and_logger] = config

    # Dispatch the partitioned configs to local/websocket-attached clients
    self.dispatch_configs(config_map)

  ############################
  def run(self):
    """Loop, checking that loggers are in the state they should be,
    getting them into that state if they aren't, and saving the resulting
    status to a StatusUpdate record in the database.

    We get the logger running status - True (running), False (not
    running but should be) or None (not running and shouldn't be) -
    and any errors.
    """
    try:
      while not self.quit_flag:
        status = {}
        for cruise_id in api.get_cruises():
          self.update_configs(cruise_id)

          # Now check up on status of all loggers that are supposed to
          # be running under this cruise_id. Because manage=True,
          # we'll restart those that are supposed to be but
          # aren't. We'll get a dict of
          #
          # { logger_id: {errors: [], running,  failed},
          #   logger_id: {...}, 
          #   logger_id: {...}
          # }
          status = self.logger_runner.check_loggers(manage=True,
                                                    clear_errors=True)
        # Write the returned statuses to data store
        api.update_status(status)

        # Nap for a bit before checking again
        time.sleep(self.interval)

    except KeyboardInterrupt:
      logging.warning('LoggerServer received keyboard interrupt - '
                      'trying to shut down nicely.')

    # Set all LoggerManagers to empty configs to shut down all their loggers
    self.logger_runner.quit()

  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True

################################################################################

################################################################################
if __name__ == '__main__':
  import argparse
  import atexit
  import readline

  from server.in_memory_server_api import InMemoryServerAPI
  from server.server_api_command_line import get_stdin_commands
  
  parser = argparse.ArgumentParser()
  parser.add_argument('--config', dest='config', action='store',
                      help='Name of cruise configuration file to load.')
  parser.add_argument('--mode', dest='mode', action='store', default=None,
                      help='Optional name of mode to start system in.')

  # Optional address for websocket server from which we'll accept
  # connections from LoggerManagers willing to accept dispatched
  # configs.
  parser.add_argument('--websocket', dest='websocket', action='store',
                      help='Host:port on which to open a websocket server '
                      'for LoggerManagers that are willing to accept config '
                      'dispatches.')

  parser.add_argument('--interval', dest='interval', action='store',
                      type=float, default=1,
                      help='How many seconds to sleep between logger checks.')
  parser.add_argument('--max_tries', dest='max_tries', action='store', type=int,
                      default=DEFAULT_MAX_TRIES,
                      help='Number of times to retry failed loggers.')

  parser.add_argument('-v', '--verbosity', dest='verbosity', default=0,
                      action='count', help='Increase output verbosity')
  parser.add_argument('-V', '--logger_verbosity', dest='logger_verbosity',
                      default=0, action='count',
                      help='Increase output verbosity of local loggers')
  args = parser.parse_args()

  # Set logging verbosity
  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  api = InMemoryServerAPI()
  logger_server = LoggerServer(api=api, websocket=args.websocket,
                               interval=args.interval, max_tries=args.max_tries,
                               verbosity=args.verbosity,
                               logger_verbosity=args.logger_verbosity)
  logger_server_thread = threading.Thread(target=logger_server.run)
  logger_server_thread.start()

  # Keep a history file around 
  histfile = os.path.join(os.path.expanduser("~"),'.rvdas_logger_server_history')
  try:
    readline.read_history_file(histfile)
    # default history len is -1 (infinite), which may grow unruly
    readline.set_history_length(1000)
  except FileNotFoundError:
    pass
  atexit.register(readline.write_history_file, histfile)

  # If they've given us an initial cruise_config, get and load it.
  if args.config:
    cruise_config = read_json(args.config)
    api.load_cruise(cruise_config)
  if args.mode:
    cruise_id = cruise_config.get('cruise', {}).get('id', None)
    if not cruise_id:
      raise ValueError('Unable to find cruise_id in specified cruise config: %s'
                       % args.config)
    api.set_mode(cruise_id, args.mode)

  # Register a callback: when api.set_mode() or api.set_config() have
  # completed, they call api.signal_update(cruise_id). We're
  # registering update_configs() with the API so that it gets called
  # when the api signals that an update has occurred.
  api.on_update(callback=logger_server.update_configs) #,
                #kwargs={'cruise_id':cruise_id},
                #cruise_id=cruise_id)

  get_commands_thread = threading.Thread(target=get_stdin_commands, args=(api,))
  get_commands_thread.start()

  if logger_server.websocket_server:

    logger_server.websocket_server.run()
  else:
    while get_commands_thread.is_alive():
      time.sleep(1)
    
  logger_server.quit()
  logger_server_thread.join()
  
  
