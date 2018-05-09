#!/usr/bin/env python3
"""Command line interface for server API.

See server/server_api.py for full documentation on the ServerAPI.
"""

import argparse
import asyncio
import json
import logging
import os
import pprint
import queue
import sys
import threading
import time

sys.path.append('.')

from logger.utils.read_json import read_json, parse_json

from server.server_api import ServerAPI

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

################################################################################
# Definitions for running from command line

############################
def get_stdin_commands(api):
  """Read stdin for commands and process them."""
  while True:
    command = input('command? ')
    process_command(command)

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
    
    #('status', 'Print current logger status to console\n'),

    ('mode <cruise_id>', 'Get current mode of specified cruise'),
    ('modes <cruise_id>', 'Get all modes of specified cruise'),
    ('set_mode <cruise_id>  <name of mode>', 'Set new current mode\n'),

    ('loggers <cruise_id>', 'Get list of loggers for specified cruise'),
    ('logger_configs <cruise_id> <logger>',
     'Get names of all configurations for specified logger'),
    ('set_logger_config_name <cruise_id> <logger name> <name of logger config>',
     'Set logger to named configuration'),
    ('set_logger_config <cruise_id> <logger name> <JSON encoding of a config>',
     'Set logger to new configuration\n'),

    ('quit', 'Quit gracefully')      
  ]
  print('Valid commands:')
  for command, desc in commands:
    print('  %s\n      %s' % (command, desc))

############################
def process_command(command):
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
    elif command.find('load_cruise ') == 0:
      (load_cmd, filename) = command.split(maxsplit=1)
      logging.info('Loading cruise config from %s', filename)
      try:
        cruise_config = read_json(filename)
        api.load_cruise(cruise_config)
      except FileNotFoundError as e:
        logging.error('Unable to find file "%s"', filename)

    # set_cruise <JSON encoding of a cruise>
    elif command.find('set_cruise ') == 0:
      (cruise_cmd, cruise_json) = command.split(maxsplit=1)
      logging.info('Setting cruise config to %s', cruise_json)
      api.load_cruise(json.loads(cruise_json))

    # delete_cruise <cruise_id>
    elif command.find('delete_cruise ') == 0:
      (cruise_cmd, cruise_id) = command.split(maxsplit=1)
      logging.info('Deleting cruise %s', cruise_id)
      api.delete_cruise(cruise_id)

    ############################
    # mode <cruise_id>
    elif command.find('mode ') == 0:
      (mode_cmd, cruise_id) = command.split(maxsplit=1)
      mode = api.get_mode(cruise_id)
      print('Current mode for %s: %s' % (cruise_id, mode))

    # modes <cruise_id>
    elif command.find('modes ') == 0:
      (mode_cmd, cruise_id) = command.split(maxsplit=1)
      modes = api.get_modes(cruise_id)
      print('Modes for %s: %s' % (cruise_id, ', '.join(modes)))

    # set_mode <cruise_id> <mode>
    elif command.find('set_mode ') == 0:
      (mode_cmd, cruise_id, mode_name) = command.split(maxsplit=2)
      logging.info('Setting mode to %s', mode_name)
      api.set_mode(cruise_id, mode_name)

    ############################
    # loggers <cruise_id>
    elif command.find('loggers ') == 0:
      (loggers_cmd, cruise_id) = command.split(maxsplit=1)
      loggers = api.get_loggers(cruise_id)
      print('Loggers for %s: %s' % (cruise_id, ', '.join(loggers)))

    # logger_configs <cruise_id> <logger>
    elif command.find('logger_configs ') == 0:
      (logger_cmd, cruise_id, logger_name) = command.split(maxsplit=2)
      logger_configs = api.get_logger_configs(cruise_id, logger_name)
      print('Configs for %s:%s: %s' %
            (cruise_id, logger_name, ', '.join(logger_configs)))
    # set_logger_config <logger name> <JSON encoding of a config>
    elif command.find('set_logger_config ') == 0:
      (logger_cmd, cruise_id, logger, config_json) = command.split(maxsplit=3)
      logging.info('Setting logger %s to config %s', logger, config_json)
      api.set_logger_config(cruise_id, logger, json.loads(config_json))

    # set_logger_config_name <cruise_id> <logger name> <name of logger config>
    elif command.find('set_logger_config_name ') == 0:
      (logger_cmd, cruise_id,
       logger_name, config_name) = command.split(maxsplit=3)
      logging.info('Setting logger %s to config %s', logger_name, config_name)

      # Is this a valid config for this logger?
      if not config_name in api.get_logger_configs(cruise_id, logger_name):
        raise ValueError('Config "%s" is not valid for logger "%s"'
                         % (config_name, logger_name))
      config = api.get_config(cruise_id, config_name)
      api.set_logger_config(cruise_id, logger_name, config)

    ## status
    #elif command == 'status':
    #  if self.console:
    #    # Do a non-updating status check
    #    status = self.logger_runner.check_loggers()
    #    print(status)

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
  import argparse
  from server.in_memory_server_api import InMemoryServerAPI

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

  api = InMemoryServerAPI()
  get_stdin_commands(api)
  
  
