#!/usr/bin/env python3
"""Start/stop loggers according passed in definitions and
commands. Depending on initialization, read further commands from
either command line or websocket.

Typical use:

  # Run the loggers from the "underway" mode of that configuration
  server/logger_manager.py --config test/configs/sample_cruise.json \
      --mode underway

(To get this to work using the sample config sample_cruise.json above,
you'll also need to run

  logger/utils/serial_sim.py --config test/serial_sim.py

in a separate terminal window to create the virtual serial ports the
sample config references and feed simulated data through them.)

If called with a --mode parameter, the script will start the logger
configurations associated with the specified mode. In the example
above, sample_cruise.json has three modes defined: off, port,
underway. If --mode is omitted, it will start in its default mode
(specified as "off" in sample_cruise.json).

If --console is specified, script will attempt to read stdin for
further commands. Valid commands are:

  load_cruise <cruise config file name>
      Load a new cruise config from file
  set_interval <seconds between updates>
      Set seconds between updates
  set_mode <name of mode>
      Set new current mode
  set_configs <JSON configs>
      Set complete configuration
  set_cruise <JSON encoding of a cruise>
      Load a new cruise config from passed JSON encoding
  set_logger_config <logger name> <JSON encoding of a config>
      Set specified logger to new configuration
  set_logger_config_name <logger name> <name of logger config>
      Set logger to named configuration
  quit
      Quit gracefully

If the --websocket <host:port> command line argument is specified,
after startup, the script will connect to the websocket and await
further commands (as above) from the websocket, and will send status
updates back to the socket at the interval specified by --interval
<seconds> (default 1).

"""
import argparse
import asyncio
import json
import logging
import pprint
import signal
import sys
import threading
import time
import websockets

sys.path.append('.')

from logger.utils.read_json import read_json
from logger.listener.listen import ListenerFromLoggerConfig

from server.logger_runner import LoggerRunner

run_logging = logging.getLogger(__name__)

############################
def kill_handler(self, signum):
  """Translate an external signal (such as we'd get from os.kill) into a
  KeyboardInterrupt, which will signal the start() loop to exit nicely."""
  logging.info('Received external kill')
  raise KeyboardInterrupt('Received external kill signal')

################################################################################
class LoggerManager:
  ############################
  def __init__(self, cruise_config=None, mode=None,
               console=False, websocket=None,
               host_id='', interval=1, max_tries=3):
    """Create a LoggerManager.

    host_id  - optional string identifier for this host that will be
          sent to websocket server to identify ourselves

    interval - number of seconds to sleep between checking/updating loggers

    max_tries - number of times to retry a dead logger config

    cruise_config - optional cruise config to load at startup

    mode - if a cruise config has been provided, the cruise mode to 
          set at startup. If omitted, cruise will be set to the default_mode
          defined in the cruise config.

    console - if True, read stdin for commands

    websocket - optional host:port address of websocket server to
          connect to for further commands. Write status back to websocket

    """      
    # Set the signal handler so that an external break will get
    # translated into a KeyboardInterrupt. But signal only works if
    # we're in the main thread - catch if we're not, and just assume
    # everything's gonna be okay and we'll get shut down with a proper
    # "quit()" call othewise.
    try:
      signal.signal(signal.SIGTERM, kill_handler)
    except ValueError:
      logging.warning('LoggerManager not running in main thread; '
                      'shutting down with Ctl-C may not work.')

    self.logger_runner = LoggerRunner(interval=interval, max_tries=max_tries)
    
    # Get any initial configuration
    self.cruise_config = None
    if cruise_config:
      self._load_cruise(cruise_config, mode)

    # Store things we're going to use later
    self.console = console
    self.websocket = websocket
    self.host_id = host_id
    self.interval = interval
    self.max_tries = max_tries
    self.quit_requested = False

    # Only let one thread process commands at a time
    self.command_lock = threading.Lock()

  ##############################################################################
  def _load_cruise(self, cruise_config, mode=None):
    """Load a cruise configuration. If mode is specified, set it in the
    specified mode, otherwise set it in its default mode."""
    self.cruise_config = cruise_config
    new_configs = self._get_configs(cruise_config, mode)
    self.logger_runner.set_configs(new_configs)

  ##############################################################################
  def _get_configs(self, cruise_config=None, mode=None):
    """Helper function: return a dict of {logger:config, ...} for given mode.
    If no cruise_config is passed, use stored one. If no mode is passed, use
    cruise_config's default_mode."""

    if cruise_config is None:
      cruise_config = self.cruise_config
    if cruise_config is None:
        raise ValueError('No cruise_config loaded')
      
    if mode is None:
      mode = cruise_config.get('default_mode', None)
      if mode is None:
        raise ValueError('No mode specified for _get_configs() and no default '
                         'mode found in cruise configuration.')
      
    loggers = cruise_config.get('loggers', None)
    if not loggers:
      raise ValueError('Cruise config has no "loggers" field')

    configs = cruise_config.get('configs', None)
    if not configs:
      raise ValueError('Cruise config has no "configs" field')

    modes = cruise_config.get('modes', None)
    if not modes:
      raise ValueError('Cruise config has no "modes" field')

    mode_configs = modes.get(mode, None)
    if mode_configs is None:
      raise ValueError('Cruise config has no mode "%s"' % mode)

    # What config each logger is/should be in
    logger_configs = {}
    for logger, logger_spec in loggers.items():
      logger_mode_config_name = mode_configs.get(logger, None)

      # If mode doesn't include a config name for logger, then logger isn't
      # running in this mode. Give it an empty config.
      if not logger_mode_config_name:
        configs[logger] = None
        continue

      # Otherwise, we've got the name of the logger's config. Verify
      # that it's a valid config for this logger, and look it up in the
      # config dict.
      valid_logger_configs = logger_spec.get('configs', None)
      if not valid_logger_configs:
        raise ValueError('Logger spec for %s has no "configs" field' % logger)
      if not logger_mode_config_name in valid_logger_configs:
        raise ValueError('Config "%s" is not valid config for logger %s '
                         '(valid configs are: %s)' %
                         (logger_mode_config_name, logger,valid_logger_configs))
      config = configs.get(logger_mode_config_name, None)
      if config is None:
        raise ValueError('No config "%s" defined for cruise.'
                         % logger_mode_config_name)
      logger_configs[logger] = config

    return logger_configs

  ############################
  def show_commands(self):
    """Print summary of commands that LoggerManager understands to stdout."""
    commands = [
      ('load_cruise <cruise config file name>',
       'Load a new cruise config from file'),
      ('set_cruise <JSON encoding of a cruise>',
       'Load a new cruise config from passed JSON encoding\n'),
      ('status', 'Print current logger status to console\n'),
      ('set_mode <name of mode>', 'Set new current mode'),
      ('set_configs <JSON configs>',
       'Set complete configuration for all loggers\n'),
      ('set_logger_config <logger name> <JSON encoding of a config>',
       'Set logger to new configuration'),
      ('set_logger_config_name <logger name> <name of logger config>',
       'Set logger to named configuration\n'),
      ('set_interval <seconds between updates>',
       'Set seconds between updates'),
      ('quit', 'Quit gracefully')      
    ]
    print('Valid commands:')
    for command, desc in commands:
      print('  %s\n      %s' % (command, desc))

  ############################
  def process_command(self, command):
    """Parse and execute the command string we've received."""
    with self.command_lock:
      # Quit gracefully
      if command == 'quit':
        logging.info('Got quit command')
        self.quit()

      # set_mode <name of mode>
      elif command.find('set_mode ') == 0:
        (mode_cmd, mode_name) = command.split(maxsplit=1)
        logging.info('Setting mode to %s', mode_name)
        try:
          configs = self._get_configs(mode=mode_name)
          self.logger_runner.set_configs(configs)
        except ValueError as e:
          logging.error('%s', e)

      # set_interval <seconds between updates>
      elif command.find('set_interval ') == 0:
        (interval_cmd, interval) = command.split(maxsplit=1)
        logging.info('Setting update interval to %s', interval)
        try:
          self.interval = float(interval)
          self.logger_runner.interval = float(interval)
        except ValueError as e:
          logging.error('%s', e)

      # set_configs <JSON encoding of complete config set>
      elif command.find('set_configs ') == 0:
        (configs_cmd, configs_str) = command.split(maxsplit=1)
        logging.info('Setting configs to %s', configs_str)
        self.logger_runner.set_configs(json.loads(config_str))

      # load_cruise <cruise config file name>
      elif command.find('load_cruise ') == 0:
        (load_cmd, filename) = command.split(maxsplit=1)
        logging.info('Loading cruise config from %s', filename)
        try:
          cruise_config = read_json(filename)
          self._load_cruise(cruise_config)
        except FileNotFoundError as e:
          logging.error('Unable to find file "%s"', filename)
        except ValueError as e:
          logging.error('%s', e)

      # set_cruise <JSON encoding of a cruise>
      elif command.find('set_cruise ') == 0:
        (cruise_cmd, cruise_json) = command.split(maxsplit=1)
        logging.info('Setting cruise config to %s', cruise_json)
        try:
          self._load_cruise(json.loads(cruise_json))
        except ValueError as e:
          logging.error('%s', e)

      # set_logger_config <logger name> <JSON encoding of a config>
      elif command.find('set_logger_config ') == 0:
        (logger_cmd, logger, config_json) = command.split(maxsplit=2)
        logging.info('Setting logger %s to config %s', logger, config_json)
        try:
          self.logger_runner.set_config(logger, json.loads(config_json))
        except ValueError as e:
          logging.error('%s', e)

      # set_logger_config_name <logger name> <name of logger config>
      elif command.find('set_logger_config_name ') == 0:
        (logger_cmd, logger_name, config_name) = command.split(maxsplit=2)
        logging.info('Setting logger %s to config %s',
                        logger_name, config_name)
        try:
          if not self.cruise_config:
            raise ValueError('No cruise config defined that would allow '
                             'setting logger config by name')
          configs = self.cruise_config.get('configs', None)
          if configs is None:
            raise ValueError('No "configs" in cruise config')
          config = configs.get(config_name, None)
          if config is None:
            raise ValueError('No config "%s" in cruise config' % config_name)
          loggers = self.cruise_config.get('loggers', None)
          if loggers is None:
            raise ValueError('No "loggers" in cruise config')
          logger = loggers.get(logger_name, None)
          if logger is None:
            raise ValueError('No logger "%s" in cruise config' % logger_name)
          logger_configs = logger.get('configs', None)
          if logger_configs is None:
            raise ValueError('Logger "%s" has no configurations?', logger_name)
          if not config_name in logger_configs:
            raise ValueError('Config "%s" is not valid for logger "%s"'
                             % (config_name, logger_name))

          self.logger_runner.set_config(logger_name, config)
        except ValueError as e:
          logging.error('%s', e)

      # status
      elif command == 'status':
        if self.console:
          # Do a non-updating status check
          status = self.logger_runner.check_loggers()
          print(status)

      else:
        print('Got unknown command: "{}"'.format(command))
        self.show_commands()
    
  ############################
  def _get_stdin_commands(self):
    """Read stdin for commands and process them."""
    while not self.quit_requested:
      command = input('command? ')
      if command:
        self.process_command(command)

  ############################
  async def _get_websocket_commands(self, websocket):
    """Listen to websocket for commands and process them."""
    async for command in websocket:
      self.process_command(command)

  ############################
  async def _check_loggers(self, websocket=None):
    """Check logger status. If websocket, send status to websocket."""
    if websocket:
      await websocket.send(json.dumps({'host_id': self.host_id}))
      
    while not self.quit_requested:
      status = self.logger_runner.check_loggers(manage=True, clear_errors=True)
      if websocket:
        await websocket.send(json.dumps({'status': status}))
        logging.info('Sent status')

      await asyncio.sleep(self.interval)
        
  ############################
  async def _logger_task_handler(self):
    """Set up two tasks in parallel: one that sends status reports and one
    that reads (and executes) commands from user/server."""
    # If we have a websocket, send status updates to it. Also listen
    # to it for command updates.
    if self.websocket:
      async with websockets.connect('ws://' + self.websocket) as websocket:
        get_commands_task = asyncio.ensure_future(
          self._get_websocket_commands(websocket))
        check_loggers_task = asyncio.ensure_future(
          self._check_loggers(websocket))
        done, pending = await asyncio.wait([get_commands_task,
                                            check_loggers_task],
                                           return_when=asyncio.FIRST_COMPLETED)
      # When here, either check_loggers_tast or get_commands_task has
      # ended. Terminate the other task.
      for task in pending:
        task.cancel()

    # If not websocket, just start logger-checking loop
    else:
      await self._check_loggers()

  ############################
  def run(self):
    """Loop, reading commands from stdin if no websocket defined; otherwise
    read commands from websocket and send status updates back."""

    # If we're a console, start reading commands from stdin
    if self.console:
      stdin_command_thread = threading.Thread(target=self._get_stdin_commands)
      stdin_command_thread.start()

    # Fire up our task loop, checking statust
    try:
      asyncio.get_event_loop().run_until_complete(self._logger_task_handler())
      
    except KeyboardInterrupt:
      logging.warning('Received KeyboardInterrupt. Exiting')

    # Wait for our input thread to terminate
    #if self.console:
    #  stdin_command_thread.join()

  ############################
  def quit(self):
    """Ask everyone to shut down gracefully."""
    self.logger_runner.quit()
    self.quit_requested = True

################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('--config', dest='config', action='store', default=None,
                      help='Name of cruise configuration file to load.')
  parser.add_argument('--mode', dest='mode', action='store', default=None,
                      help='Optional name of mode to start system in.')

  parser.add_argument('--console', dest='console', action='store_true',
                      help='If specified, attempt to read stdin for further '
                      'commands')
  parser.add_argument('--websocket', dest='websocket', action='store', type=str,
                      default=None, help='If specified, connect to websocket '
                      'and attempt to read for further commands. Send logger '
                      'status updates to the same websocket.')
  parser.add_argument('--host_id', dest='host_id', action='store', default='',
                      help='Host ID to send to websocket to identify ourselves')

  parser.add_argument('--interval', dest='interval', action='store',
                      type=float, default=1,
                      help='How many seconds to sleep between logger checks.')
  parser.add_argument('--max_tries', dest='max_tries', action='store',
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
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
  run_logging.setLevel(LOG_LEVELS[args.logger_verbosity])
  
  if args.console and args.websocket:
    logging.error('Can not specify both --console and --websocket')
    sys.exit(1)
  
  cruise_config = read_json(args.config) if args.config else None
    
  manager = LoggerManager(cruise_config=cruise_config, mode=args.mode,
                          console=args.console, websocket=args.websocket,
                          host_id=args.host_id, interval=args.interval,
                          max_tries=args.max_tries)
  manager.run()

