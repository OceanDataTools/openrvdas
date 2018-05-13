#!/usr/bin/env python3
"""LoggerServers get their desired state of the world via a ServerAPI
instance and attempt to start/stop loggers with the desired configs
by dispatching requests to a local LoggerRunner.

To run the LoggerManager from the command line with (using the default
of an InMemoryServerAPI):

  server/logger_manager.py

If an initial cruise config is specified on the command line, as
below:

  server/logger_manager.py --config test/configs/sample_cruise.json

the cruise configuration will be loaded and set to its default
mode. If a --mode argument is included, it will be used in place of
the default mode.

If the LoggerManager is created with a websocket specification
(host:port), it will accept connections from LoggerRunners. It
expects the LoggerRunners to identify themselves with a host_id, and
will dispatch any configs listing that host_id to the appropriate
LoggerRunner. Configs that have no host_id specified will continue to
be dispatched to the local LoggerRunner; configs specifying a host_id
that doesn't match any connected LoggerRunner will not be run:

  server/logger_manager.py --websocket localhost:8765

A LoggerRunner that would connect to the above LoggerManager could be
launched via:

  server/logger_runner.py --websocket localhost:8765 \
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

3. In the third one, start a LoggerManager with a websocket server:

   server/logger_manager.py --config test/configs/sample_cruise.json \
         --websocket localhost:8765 -v

4. In the fourth one, start a LoggerRunner that will try to connect
   to the websocket on the LoggerManager you've started.

   server/logger_runner.py --websocket localhost:8765 \
         --host_id knud.host -v

   Note that this LoggerRunner is identifying its host as
   "knud.host"; if you look at sample_cruise.json, you'll notice that
   the configs for the "knud" logger have a host restriction of
   "knud.host", meaning that our LoggerManager should try to dispatch
   those configs to this LoggerRunner.

5. In the terminal running the LoggerManager, try a few commands:

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
   LoggerManager window.

   When setting the mode to underway, you should see more data
   appearing in the listener window (due to more logger configs
   running), and should see the LoggerRunner leap into action as the
   LoggerManager dispatches the configs for "knud.host" to it.

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

from logger.utils.read_json import read_json

from server.server_api import ServerAPI
from server.logger_runner import LoggerRunner, run_logging

# Number of times we'll try a failing logger before giving up
DEFAULT_MAX_TRIES = 3

# To keep logger/config names unique, we'll prepend cruise_id,
# separating them by CRUISE_ID_SEPARATOR; e.g. NBP1700:knud
CRUISE_ID_SEPARATOR = ':'

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

################################################################################
class LoggerManager:
  ############################
  def __init__(self, api=None, websocket=None, host_id=None,
               interval=0.5, max_tries=3,
               verbosity=0, logger_verbosity=0):
    """Read desired/current logger configs from Django DB and try to run the
    loggers specified in those configs.

    api - ServerAPI (or subclass) instance by which LoggerManager will get
          its data store updates

    websocket - optional host:port on which to open a websocket server
          for LoggerRunners to connect to for dispatches of logger
          configs they should run.

    host_id - optional id by which we identify ourselves. Tasks that
         include a "host_id" specification will only be dispatched to
         the matching host. For now, all tasks without a host_id
         specification will be run on the local machine.

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
    self.host_id = host_id or None
    self.interval = interval
    self.max_tries = max_tries
    self.quit_flag = False
    self.websocket_server = None

    # Keep track of old configs so we only send updates to the
    # LoggerRunners when things change.
    self.old_configs = {}
    self.config_lock = threading.Lock()
    
    # Create our own LoggerRunner to use by default when configs don't
    # specify a host restriction. (NOTE: we really ought to find a way
    # to load balance and not take on all unrestricted configs
    # ourselves.)
    self.logger_runner = LoggerRunner(interval=self.interval,
                                      max_tries=self.max_tries)

    # Maps between client_id and host_id. To facilitate simplicity of
    # handling code elsewhere, we assign the client_id of our "local"
    # LoggerRunner to be None.
    self.host_id_to_client = {self.host_id:None}
    self.client_to_host_id = {None:self.host_id}
    self.send_queue = {}     # client_id->queue for messages to send to ws
    self.receive_queue = {}  # client_id->queue for messages from ws

    # A lock to make sure only one thread is messing with the above
    # maps at any given time.
    self.client_map_lock = threading.Lock()

    # Has caller directed us to launch a Websocket server where other
    # LoggerRunners can connect? 
    if websocket:
      from server.websocket_server import WebsocketServer
      try:
        host, port_str = args.websocket.split(':')
        port = int(port_str)
        self.websocket_server = WebsocketServer(
          host=host, port=port,
          consumer=self.queued_consumer,
          producer=self.queued_producer,
          on_connect=self.register_client,
          on_disconnect=self.unregister_client)
        #self.websocket_server.run()
      except ValueError as e:
        logging.error('--websocket arg "%s" not in host:port format',
                      args.websocket)
        exit(1)

  ##########################
  # "Consumes" a message (typically received by the websocket) by
  # putting it on the "received" queue
  async def queued_consumer(self, message, client_id):
   logging.debug('Received message from client #%d: %s', client_id, message)
   self.receive_queue[client_id].put(message)
    
  ############################
  # "Produces" and returns message (typically from the "send" queue)
  # to be sent by the websocket.
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
    """Assign the passed configs to the named host_id. If host_id matches
    self.host_id, then assign the configs to our local LoggerRunner."""
    if configs:
      logging.info('Dispatching configs for host %s', host_id or 'local')
    else:
      logging.info('No configs for host %s', host_id or 'local')

    if host_id == self.host_id:
      self.logger_runner.set_configs(configs)
      return

    # If here, we need to dispatch somewhere non-local
    if not self.websocket_server:
      logging.error('No websocket server - unable to dispatch '
                    'tasks for host_id "%s"', host_id)
      return
    client_id = self.host_id_to_client.get(host_id, None)
    if client_id is None:
      logging.error('No host %s available for dispatched tasks', host_id)
      return

    # If here, we're ready to dispatch
    command = 'set_configs ' + json.dumps(configs)
    self.send_queue[client_id].put(command)

  ############################
  def dispatch_configs(self, config_map):
    """We're passed a dict mapping host_ids to sets of configs.  Dispatch
    the configs to their respective hosts."""

    with self.config_lock:
      # First, see if there are any configs we're supposed to dispatch
      # for which we don't have the appropriate host.
      for desired_host in config_map:
        if not desired_host in self.host_id_to_client:
          logging.warning('Unable to dispatch configs to "%s" - no such host',
                          desired_host)
      # For each of our registered clients, see if we have any configs
      # in the config_map for them to run. If not, assign them an
      # empty config ({}) so that they're not running anything.
      for host_id, client_id in self.host_id_to_client.items():
        desired_config = config_map.get(host_id, {})
        self._set_host_configs(host_id, desired_config)

  ############################
  def update_configs(self, cruise_id=None):
    """Check the API for updated configs for cruise_id, and send them to
    the appropriate LoggerRunner. If cruise_id is None, check for all
    cruises."""
    # Get latest configs.
    with self.config_lock:
      if cruise_id:
        new_configs = {cruise_id: self.api.get_configs(cruise_id) }
      else:
        new_configs = {cruise_id: self.api.get_configs(cruise_id)
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
        # under key self.host_id (which may be 'None') to run locally.
        logging.debug('Config for logger %s, cruise %s: %s',
                        logger, cruise_id, config)
        if not config:
          continue
        host_id = config.get('host_id', self.host_id)
        if not host_id in config_map:
          config_map[host_id] = {}
        cruise_and_logger = cruise_id + CRUISE_ID_SEPARATOR + logger
        config_map[host_id][cruise_and_logger] = config

    # Dispatch the partitioned configs to local/websocket-attached clients
    self.dispatch_configs(config_map)

  ############################
  def process_response(self, response, client_id=None):
    """Process responses we get from connected clients. A client_id of
    None means it's from our local LoggerRunner."""
    status = response.get('status', None)
    if status:
      logging.info('Got status from %s', client_id or 'local')
      self.api.update_status(status)

    errors = response.get('errors', None)
    if errors:
      logging.error('Errors from client %s: %s', client_id or 'local', errors)

    # Note: clients who don't provide a host_id don't get registered
    # in the host-client maps, and thus will never get any jobs
    # assigned to them.
    host_id = response.get('host_id', None)
    if host_id is not None:
      logging.info('Got host_id "%s" from client %s', host_id, client_id)
      self.host_id_to_client[host_id] = client_id
      self.client_to_host_id[client_id] = host_id

  ############################
  def register_client(self, websocket, client_id):
    """We've been alerted that a websocket client has connected.
    Create send/receive queues for it."""
    with self.client_map_lock:
      # If we haven't created queues for it yet, do that now
      if not client_id in self.send_queue:
        self.send_queue[client_id] = queue.Queue()
        self.receive_queue[client_id] = queue.Queue()

  ############################
  def unregister_client(self, client_id):
    """We've been alerted that a websocket client has disconnected.
    Unregister it properly. NOTE: SHOULDN'T WE PROCESS EVERYTHING IN
    THESE QUEUES BEFORE DISCONNECTING?"""
    with self.client_map_lock:
      if client_id in self.send_queue: del self.send_queue[client_id]
      if client_id in self.receive_queue: del self.receive_queue[client_id]
      
      if client_id in self.client_to_host_id:
        host_id = self.client_to_host_id[client_id]
        del self.host_id_to_client[host_id]
        del self.client_to_host_id[client_id]
      logging.warning('Client #%d (%s)has disconnected', client_id, host_id)

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
        # Check for new configs and send them out
        self.update_configs()

        # Now check up on status of all loggers that are supposed to
        # be running. Because manage=True, we'll restart those that
        # are supposed to be but aren't. We'll get a dict of
        #
        # { cruise_id:logger_id: {errors: [], running,  failed},
        #   cruise_id:logger_id: {...}, 
        #   cruise_id:logger_id: {...}
        # }

        # First check up on our local LoggerRunner. Wrap its status
        # response with a 'status' tag before passing it along for
        # processing.
        status = self.logger_runner.check_loggers(manage=True,clear_errors=True)
        response = {'status': status}
        self.process_response(response, client_id=None)

        # Now iterate through our clients, grabbing response from each
        # in turn (for fairness) until we've got them all.  NOTE: THIS
        # SHOULD BE IN A SEPARATE THREAD!
        while True:
          got_response = False
          for client_id, receive_queue in self.receive_queue.items():
            try:
              response_str = self.receive_queue[client_id].get_nowait()
              response = json.loads(response_str)
              logging.info('Client %s sent: %s',
                              client_id, ', '.join(response.keys()))
              self.process_response(response, client_id)
              got_response = True
            except queue.Empty:
              pass
          if not got_response:
            break
        logging.debug('Done getting responses')

        # Nap for a bit before checking again
        time.sleep(self.interval)

    except KeyboardInterrupt:
      logging.warning('LoggerManager received keyboard interrupt - '
                      'trying to shut down nicely.')

    # Set all LoggerRunners to empty configs to shut down all their loggers
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
  # connections from LoggerRunners willing to accept dispatched
  # configs.
  parser.add_argument('--websocket', dest='websocket', action='store',
                      help='Host:port on which to open a websocket server '
                      'for LoggerRunners that are willing to accept config '
                      'dispatches.')
  parser.add_argument('--host_id', dest='host_id', action='store', default='',
                      help='Host ID by which we identify ourselves')

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
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  api = InMemoryServerAPI()
  logger_manager = LoggerManager(api=api, websocket=args.websocket,
                                 host_id=args.host_id,
                                 interval=args.interval,
                                 max_tries=args.max_tries,
                                 verbosity=args.verbosity,
                                 logger_verbosity=args.logger_verbosity)
  logger_manager_thread = threading.Thread(target=logger_manager.run)
  logger_manager_thread.start()

  # Keep a history file around 
  histfile = os.path.join(os.path.expanduser("~"),
                          '.rvdas_logger_manager_history')
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
  api.on_update(callback=logger_manager.update_configs) #,
                #kwargs={'cruise_id':cruise_id},
                #cruise_id=cruise_id)

  get_commands_thread = threading.Thread(target=get_stdin_commands, args=(api,))
  get_commands_thread.start()

  if logger_manager.websocket_server:
    logger_manager.websocket_server.run()

  get_commands_thread.join() 
  logger_manager.quit()
  logger_manager_thread.join()
  
  
