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
import json
import logging
import os
import pprint
import readline
import sys

sys.path.append('.')

from logger.utils.read_json import read_json
from server.server_api import ServerAPI

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

################################################################################
# Definitions for running from command line

############################
def get_stdin_commands(api):
  """Read stdin for commands and process them."""
  if not issubclass(type(api), ServerAPI):
    raise ValueError('Passed api "%s" must be subclass of ServerAPI' % api)

  while True:
    command = input('command? ')
    process_command(api, command)

############################
def show_commands():
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
    
    ('quit', 'Quit gracefully')      
  ]
  print('Valid commands:')
  for command, desc in commands:
    print('  %s\n      %s' % (command, desc))

############################
def process_command(api, command):
  """Parse and execute the command string we've received."""
  # cruises
  try:
    if command == 'cruises':
      cruises = api.get_cruises()
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
        api.load_cruise(cruise_config)
      except FileNotFoundError as e:
        logging.error('Unable to find file "%s"', filename)

    # set_cruise <JSON encoding of a cruise>
    elif command == 'set_cruise':
      raise ValueError('format: set_cruise <JSON encoding of a cruise')
    elif command.find('set_cruise ') == 0:
      (cruise_cmd, cruise_json) = command.split(maxsplit=1)
      logging.info('Setting cruise config to %s', cruise_json)
      api.load_cruise(json.loads(cruise_json))

    # delete_cruise <cruise_id>
    elif command == 'delete_cruise':
      raise ValueError('format: delete_cruise <cruise id>')
    elif command.find('delete_cruise ') == 0:
      (cruise_cmd, cruise_id) = command.split(maxsplit=1)
      logging.info('Deleting cruise %s', cruise_id)
      api.delete_cruise(cruise_id)

    ############################
    # mode <cruise_id>
    elif command == 'mode':
      raise ValueError('format: mode <cruise id>')
    elif command.find('mode ') == 0:
      (mode_cmd, cruise_id) = command.split(maxsplit=1)
      mode = api.get_mode(cruise_id)
      print('Current mode for %s: %s' % (cruise_id, mode))

    # modes <cruise_id>
    elif command == 'modes':
      raise ValueError('format: modes <cruise id>')
    elif command.find('modes ') == 0:
      (mode_cmd, cruise_id) = command.split(maxsplit=1)
      modes = api.get_modes(cruise_id)
      print('Modes for %s: %s' % (cruise_id, ', '.join(modes)))

    # set_mode <cruise_id> <mode>
    elif command == 'set_mode':
      raise ValueError('format: set_mode <cruise id> <mode>')
    elif command.find('set_mode ') == 0:
      (mode_cmd, cruise_id, mode_name) = command.split(maxsplit=2)
      logging.info('Setting mode to %s', mode_name)
      api.set_mode(cruise_id, mode_name)

    ############################
    # loggers <cruise_id>
    elif command == 'loggers':
      raise ValueError('format: loggers <cruise id>')
    elif command.find('loggers ') == 0:
      (loggers_cmd, cruise_id) = command.split(maxsplit=1)
      loggers = api.get_loggers(cruise_id)
      print('Loggers for %s: %s' % (cruise_id, ', '.join(loggers)))

    # logger_configs <cruise_id> <logger>
    elif command == 'logger_configs':
      raise ValueError('format: logger_configs <cruise_id> <logger>')
    elif command.find('logger_configs ') == 0:
      (logger_cmd, cruise_id, logger_name) = command.split(maxsplit=2)
      logger_configs = api.get_logger_config_names(cruise_id, logger_name)
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
      if not config_name in api.get_logger_config_names(cruise_id, logger_name):
        raise ValueError('Config "%s" is not valid for logger "%s"'
                         % (config_name, logger_name))
      api.set_logger_config_name(cruise_id, logger_name, config_name)

    # configs <cruise_id>
    elif command == 'configs':
      raise ValueError('format: configs <cruise id>')
    elif command.find('configs ') == 0:
      (config_cmd, cruise_id) = command.split(maxsplit=1)
      config_names = {logger_id:api.get_logger_config_name(cruise_id, logger_id)
                 for logger_id in api.get_loggers(cruise_id)}
      for logger_id, config_name in config_names.items():
        print('%s: %s' % (logger_id, config_name))

    # status
    elif command == 'status':
      raise ValueError('format: status <cruise id>')
    elif command.find('status ') == 0:
      (status_cmd, cruise_id) = command.split(maxsplit=1)
      status_dict = api.get_status(cruise_id)
      print('%s' % pprint.pformat(status_dict))

    # status_since
    elif command == 'status_since':
      raise ValueError('format: status_since <cruise id> <timestamp>')
    elif command.find('status_since ') == 0:
      (status_cmd, cruise_id, since_timestamp) = command.split(maxsplit=2)
      status_dict = api.get_status(cruise_id, float(since_timestamp))
      print('%s' % pprint.pformat(status_dict))

    # Quit gracefully
    elif command == 'quit':
      logging.info('Got quit command')
      exit(0)
      
    elif command == 'help':
      show_commands()
      
    else:
      print('Got unknown command: "{}"'.format(command))
      print('Type "help" for help')

  except ValueError as e:
    logging.error('%s', e)
    
################################################################################
if __name__ == '__main__':
  from server.in_memory_server_api import InMemoryServerAPI
  from gui.django_server_api import DjangoServerAPI

  parser = argparse.ArgumentParser()
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

  # Keep a history file around 
  histfile = os.path.join(os.path.expanduser("~"),'.rvdas_command_line_history')
  try:
    readline.read_history_file(histfile)
    # default history len is -1 (infinite), which may grow unruly
    readline.set_history_length(1000)
  except FileNotFoundError:
    pass
  atexit.register(readline.write_history_file, histfile)

  # Create API and start taking commands
  #  api = InMemoryServerAPI()
  api = DjangoServerAPI()
  get_stdin_commands(api)
  
  
