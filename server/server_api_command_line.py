#!/usr/bin/env python3
"""Command line interface for server API.

Includes a script that maintains an InMemoryServerAPI instance and
allows you to modify it. Run via

    server/server_api_command_line.py

and type "help" for list of valid commands.

Also see server/server_api.py for full documentation on the ServerAPI.
"""

import argparse
import atexit
import getpass  # to get username
import json
import logging
import os
import pprint
import readline
import signal
import socket  # to get hostname
import sys

sys.path.append('.')

from logger.utils.read_json import read_json
from server.server_api import ServerAPI

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

SOURCE_NAME = 'ServerAPICommandLine'
USER = getpass.getuser()
HOSTNAME = socket.gethostname()

############################
def kill_handler(self, signum):
  """Translate an external signal (such as we'd get from os.kill) into a
  KeyboardInterrupt, which will signal the start() loop to exit nicely."""
  raise KeyboardInterrupt('Received external kill signal')

################################################################################
# Definitions for running from command line
class ServerAPICommandLine:
  def __init__(self, api):
    """Argument api is a ServerAPI subclass instance, either an
    InMemoryServerAPI or DjangoServerAPI as of this writing.
    """
    if not issubclass(type(api), ServerAPI):
      raise ValueError('Passed api "%s" must be subclass of ServerAPI' % api)
    self.api = api
    self.quit_requested = False

    try:
      signal.signal(signal.SIGTERM, kill_handler)
    except ValueError:
      logging.info('ServerAPICommandLine not running in main thread; '
                   'shutting down with Ctl-C may not work.')    

  ############################
  def quit(self):
    logging.info('ServerAPICommandLine - quit requested')
    self.quit_requested = True
    
  ############################
  def run(self):
    """Iterate, reading commands and processing them."""
    try:
      self.api.message_log(SOURCE_NAME, '(%s@%s)' % (USER, HOSTNAME),
                           self.api.INFO, 'started')
      while not self.quit_requested:
        command = input('command? ')
        if command:
          command = command.strip()
          self.process_command(command)

    except (KeyboardInterrupt, EOFError):
      logging.warning('ServerAPICommandLine.run() received Keyboard Interrupt')

    # Signal cleanup
    self.quit()

  ############################
  def show_commands(self):
    """Print summary of commands we can send to API."""
    commands = [
      ('cruises', 'Show list of loaded cruises'),
      ('load_cruise <cruise config file name>',
       'Load a new cruise config from file'),
      ('set_cruise <JSON encoding of a cruise>',
       'Load a new cruise config from passed JSON encoding'),
      ('delete_cruise <cruise id>',
       'Delete a cruise from the server\n'),

      ('mode <cruise_id>', 'Get current mode of specified cruise'),
      ('modes <cruise_id>', 'Get all modes of specified cruise'),
      ('set_mode <cruise_id>  <name of mode>', 'Set new current mode\n'),

      ('loggers <cruise_id>', 'Get list of loggers for specified cruise'),
      ('configs <cruise_id>', 'Get names of current configurations cruise id\n'),

      ('logger_configs <cruise_id> <logger>',
       'Get names of all configurations for specified logger'),
      ('set_logger_config_name <cruise_id> <logger name> <name of logger config>',
       'Set logger to named configuration\n'),

      ('status <cruise_id>',
       'Print most recent status for each logger in cruise'),
      ('status_since <cruise_id> <timestamp>',
       'Get all logger status updates since specified timestamp\n'),

      ('server_log [timestamp]',
       'Print most recent log message for server, optionally all messages '
       'since specified timestamp\n'),

      ('quit', 'Quit gracefully')      
    ]
    print('Valid commands:')
    for command, desc in commands:
      print('  %s\n      %s' % (command, desc))

  ############################
  def process_command(self, command):
    """Parse and execute the command string we've received."""
    # cruises
    try:
      if not command:
        logging.info('Empty command received')
        
      elif command == 'cruises':
        cruises = self.api.get_cruises()
        if cruises:
          print('Loaded cruises: ' + ', '.join(cruises))
        else:
          print('No cruises loaded')

      # load_cruise <cruise config file name>
      elif command == 'load_cruise':
        raise ValueError('format: load_cruise <cruise config file name>')
      elif command.find('load_cruise ') == 0:
        (load_cmd, filename) = command.split(maxsplit=1)
        logging.info('Loading cruise config from %s', filename)
        try:
          cruise_config = read_json(filename)
          self.api.load_cruise(cruise_config)
        except FileNotFoundError as e:
          logging.error('Unable to find file "%s"', filename)

      # set_cruise <JSON encoding of a cruise>
      elif command == 'set_cruise':
        raise ValueError('format: set_cruise <JSON encoding of a cruise')
      elif command.find('set_cruise ') == 0:
        (cruise_cmd, cruise_json) = command.split(maxsplit=1)
        logging.info('Setting cruise config to %s', cruise_json)
        self.api.load_cruise(json.loads(cruise_json))

      # delete_cruise <cruise_id>
      elif command == 'delete_cruise':
        raise ValueError('format: delete_cruise <cruise id>')
      elif command.find('delete_cruise ') == 0:
        (cruise_cmd, cruise_id) = command.split(maxsplit=1)
        logging.info('Deleting cruise %s', cruise_id)
        self.api.delete_cruise(cruise_id)

      ############################
      # mode <cruise_id>
      elif command == 'mode':
        raise ValueError('format: mode <cruise id>')
      elif command.find('mode ') == 0:
        (mode_cmd, cruise_id) = command.split(maxsplit=1)
        mode = self.api.get_mode(cruise_id)
        print('Current mode for %s: %s' % (cruise_id, mode))

      # modes <cruise_id>
      elif command == 'modes':
        raise ValueError('format: modes <cruise id>')
      elif command.find('modes ') == 0:
        (mode_cmd, cruise_id) = command.split(maxsplit=1)
        modes = self.api.get_modes(cruise_id)
        print('Modes for %s: %s' % (cruise_id, ', '.join(modes)))

      # set_mode <cruise_id> <mode>
      elif command == 'set_mode':
        raise ValueError('format: set_mode <cruise id> <mode>')
      elif command.find('set_mode ') == 0:
        (mode_cmd, cruise_id, mode_name) = command.split(maxsplit=2)
        logging.info('Setting mode to %s', mode_name)
        self.api.set_mode(cruise_id, mode_name)

      ############################
      # loggers <cruise_id>
      elif command == 'loggers':
        raise ValueError('format: loggers <cruise id>')
      elif command.find('loggers ') == 0:
        (loggers_cmd, cruise_id) = command.split(maxsplit=1)
        loggers = self.api.get_loggers(cruise_id)
        print('Loggers for %s: %s' % (cruise_id, ', '.join(loggers)))

      # logger_configs <cruise_id> <logger>
      elif command == 'logger_configs':
        raise ValueError('format: logger_configs <cruise_id> <logger>')
      elif command.find('logger_configs ') == 0:
        (logger_cmd, cruise_id, logger_name) = command.split(maxsplit=2)
        logger_configs = self.api.get_logger_config_names(cruise_id, logger_name)
        print('Configs for %s:%s: %s' %
              (cruise_id, logger_name, ', '.join(logger_configs)))

      # set_logger_config_name <cruise_id> <logger name> <name of logger config>
      elif command == 'set_logger_config_name':
        raise ValueError('format: set_logger_config_name <cruise_id> <logger name> <name of logger config>')
      elif command.find('set_logger_config_name ') == 0:
        (logger_cmd, cruise_id,
         logger_name, config_name) = command.split(maxsplit=3)
        logging.info('Setting logger %s to config %s', logger_name, config_name)

        # Is this a valid config for this logger?
        if not config_name in self.api.get_logger_config_names(cruise_id, logger_name):
          raise ValueError('Config "%s" is not valid for logger "%s"'
                           % (config_name, logger_name))
        self.api.set_logger_config_name(cruise_id, logger_name, config_name)

      # configs <cruise_id>
      elif command == 'configs':
        raise ValueError('format: configs <cruise id>')
      elif command.find('configs ') == 0:
        (config_cmd, cruise_id) = command.split(maxsplit=1)
        config_names = {logger_id:self.api.get_logger_config_name(cruise_id, logger_id)
                   for logger_id in self.api.get_loggers(cruise_id)}
        for logger_id, config_name in config_names.items():
          print('%s: %s' % (logger_id, config_name))

      # status
      elif command == 'status':
        raise ValueError('format: status <cruise id>')
      elif command.find('status ') == 0:
        (status_cmd, cruise_id) = command.split(maxsplit=1)
        status_dict = self.api.get_status(cruise_id)
        print('%s' % pprint.pformat(status_dict))

      # status_since
      elif command == 'status_since':
        raise ValueError('format: status_since <cruise id> <timestamp>')
      elif command.find('status_since ') == 0:
        (status_cmd, cruise_id, since_timestamp) = command.split(maxsplit=2)
        status_dict = self.api.get_status(cruise_id, float(since_timestamp))
        print('%s' % pprint.pformat(status_dict))

      # server_log
      elif command == 'server_log':
        server_log = self.api.get_message_log(source=SOURCE_NAME)
        print('%s' % pprint.pformat(server_log))

      # server_log timestamp
      elif command.find('server_log') == 0:
        (log_cmd, since_timestamp) = command.split(maxsplit=1)
        server_log = self.api.get_message_log(source=SOURCE_NAME, user=None,
          log_level=self.api.DEBUG, since_timestamp=float(since_timestamp))
        print('%s' % pprint.pformat(server_log))

      # Quit gracefully
      elif command == 'quit':
        logging.info('Got quit command')
        self.quit()

      elif command == 'help':
        self.show_commands()

      else:
        print('Got unknown command: "{}"'.format(command))
        print('Type "help" for help')

    except ValueError as e:
      logging.error('%s', e)
    finally:
      self.api.message_log(SOURCE_NAME, '(%s@%s)' % (USER, HOSTNAME),
                            self.api.INFO, 'command: '+ command)
    
################################################################################
if __name__ == '__main__':

  parser = argparse.ArgumentParser()
  parser.add_argument('--database', dest='database', action='store',
                      choices=['memory', 'django'],
                      default='memory', help='What backing store database '
                      'to use. Currently-implemented options are "memory" '
                      'and "django".')
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  parser.add_argument('-V', '--logger_verbosity', dest='logger_verbosity',
                      default=0, action='count',
                      help='Increase output verbosity of component loggers')
  args = parser.parse_args()

  # Set logging verbosity
  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  # Enable command line editing and history
  histfile = '.openrvdas_command_line_history'
  histpath = os.path.join(os.path.expanduser('~'), histfile)
  try:
    readline.read_history_file(histpath)
    # default history len is -1 (infinite), which may grow unruly
    readline.set_history_length(1000)
  except (FileNotFoundError, PermissionError):
    pass
  atexit.register(readline.write_history_file, histpath)

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
  else:
    raise ValueError('Illegal arg for --database: "%s"' % args.database)
  command_line_reader = ServerAPICommandLine(api)
  command_line_reader.run()


  
  
