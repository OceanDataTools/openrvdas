#!/usr/bin/env python3
"""Command line interface for server API.

Includes a script that maintains an InMemoryServerAPI instance and
allows you to modify it. Run via
```
    server/server_api_command_line.py
```
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

from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))
from logger.utils.read_config import read_config  # noqa: E402
from server.server_api import ServerAPI  # noqa: E402

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}

SOURCE_NAME = 'CommandLine'
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
        self.api.quit()

    ############################
    def run(self):
        """Iterate, reading commands and processing them."""
        try:
            self.api.message_log(source=SOURCE_NAME,
                                 user='(%s@%s)' % (USER, HOSTNAME),
                                 log_level=self.api.INFO,
                                 message='started')
            while not self.quit_requested:
                command = input('command? ')
                if command:
                    command = command.strip()
                    self.process_command(command)

        except (KeyboardInterrupt, EOFError):
            logging.warning('ServerAPICommandLine.run() received Keyboard Interrupt')
        except Exception as e:
            logging.error(str(e))

        # Signal cleanup
        self.quit()

    ############################
    def show_commands(self):
        """Print summary of commands we can send to API."""
        commands = [
            # ('cruises', 'Show list of loaded cruises'),
            ('load_configuration <configuration file name>',
             'Load a new config from file and set to default mode'),
            ('reload_configuration',
             'Reload the current configuration file and update any loggers whose '
             'that configurations have changed'),
            ('set_configuration <JSON encoding of a configuration>',
             'Load a new configuration from passed JSON encoding'),
            ('delete_configuration',
             'Delete the current configuration from the server\n'),

            ('get_active_mode', 'Get currently active mode'),
            ('get_modes', 'Get list of all defined modes'),
            ('set_active_mode <name of mode>', 'Set new current mode\n'),

            ('get_loggers', 'Get list of all defined loggers'),
            ('get_active_logger_configs', 'Get names of active logger configurations\n'),

            ('get_logger_configs <logger>',
                'Get names of all configurations for specified logger'),
            ('set_active_logger_config <logger name> <name of logger config>',
                'Set logger to named configuration\n'),

            ('get_status',
                'Print most recent status for each logger'),
            ('get_status_since <timestamp>',
                'Get all logger status updates since specified timestamp\n'),

            ('get_server_log [timestamp]',
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
        try:
            if not command:
                logging.info('Empty command received')

            # elif command == 'cruises':
            #   cruises = self.api.get_cruises()
            #   if cruises:
            #     print('Loaded cruises: ' + ', '.join(cruises))
            #   else:
            #     print('No cruises loaded')

            # load_configuration <cruise config file name>
            elif command == 'load_configuration':
                raise ValueError('format: load_configuration <config file name>')
            elif command.find('load_configuration ') == 0:
                (load_cmd, filename) = command.split(maxsplit=1)
                logging.info('Loading config from %s', filename)
                try:
                    # Load the file to memory and parse to a dict. Add the name
                    # of the file we've just loaded to the dict.
                    config = read_config(filename)
                    if 'cruise' in config:
                        config['cruise']['config_filename'] = filename
                    self.api.load_configuration(config)
                    default_mode = self.api.get_default_mode()
                    if default_mode:
                        self.api.set_active_mode(default_mode)
                except FileNotFoundError:
                    logging.error('Unable to find file "%s"', filename)

            # reload_configuration <cruise config file name>
            # Main difference here is that we already have the filename, and
            # we *don't* reset everything to the default mode after loading.
            elif command == 'reload_configuration':
                try:
                    # Look up the filename of the current cruise_definition.
                    cruise = self.api.get_configuration()
                    filename = cruise['config_filename']

                    # Load the file to memory and parse to a dict. Add the name
                    # of the file we've just loaded to the dict.
                    config = read_config(filename)
                    if 'cruise' in config:
                        config['config_filename'] = filename
                    self.api.load_configuration(config)
                except FileNotFoundError:
                    logging.error('Unable to find file "%s"', filename)

            # set_cruise <JSON encoding of a cruise>
            elif command == 'set_configuration':
                raise ValueError('format: set_configuration <JSON encoding of config>')
            elif command.find('set_configuration ') == 0:
                (cruise_cmd, config_json) = command.split(maxsplit=1)
                logging.info('Setting config to %s', config_json)
                self.api.load_configuration(json.loads(config_json))
                default_mode = self.api.get_default_mode()
                if default_mode:
                    self.api.set_active_mode(default_mode)

            # delete_cruise <cruise_id>
            # elif command == 'delete_configuration':
            #   raise ValueError('format: delete_configuration')
            elif command.find('delete_configuration') == 0:
                logging.info('Deleting config')
                self.api.delete_configuration()

            # modes <cruise_id>
            # elif command == 'modes':
            #   raise ValueError('format: modes')
            elif command.find('get_modes') == 0:
                (mode_cmd) = command.split(maxsplit=1)
                modes = self.api.get_modes()
                if len(modes) > 0:
                    print('Available Modes: %s' % (', '.join(modes)))
                else:
                    print('Available Modes: n/a')

            ############################
            # mode <cruise_id>
            # elif command == 'mode':
            #   raise ValueError('format: mode')
            elif command.find('get_active_mode') == 0:
                (mode_cmd) = command.split(maxsplit=1)
                mode = self.api.get_active_mode()
                print('Current mode: %s' % (mode))

            # set_active_mode <mode>
            elif command == 'set_active_mode':
                raise ValueError('format: set_active_mode <mode>')
            elif command.find('set_active_mode ') == 0:
                (mode_cmd, mode_name) = command.split(maxsplit=1)
                logging.info('Setting mode to %s', mode_name)
                self.api.set_active_mode(mode_name)

            ############################
            # loggers <cruise_id>
            # elif command == 'loggers':
            #   raise ValueError('format: loggers')
            elif command.find('get_loggers') == 0:
                loggers = self.api.get_loggers()
                if len(loggers) > 0:
                    print('Loggers: %s' % (', '.join(loggers)))
                else:
                    print('Loggers: n/a')

            ############################
            # logger_configs <cruise_id> <logger>
            elif command == 'get_logger_configs':
                raise ValueError('format: get_logger_configs <logger name>')
            elif command.find('get_logger_configs ') == 0:
                (logger_cmd, logger_name) = command.split(maxsplit=1)
                logger_configs = self.api.get_logger_config_names(logger_name)
                print('Configs for %s: %s' %
                      (logger_name, ', '.join(logger_configs)))

            ############################
            # set_logger_config_name <cruise_id> <logger name> <name of logger config>
            elif command == 'set_active_logger_config':
                raise ValueError(
                    'format: set_active_logger_config <logger name> <name of logger config>')
            elif command.find('set_active_logger_config ') == 0:
                (logger_cmd,
                 logger_name, config_name) = command.split(maxsplit=2)
                logging.info('Setting logger %s to config %s', logger_name, config_name)

                # Is this a valid config for this logger?
                if config_name not in self.api.get_logger_config_names(logger_name):
                    raise ValueError('Config "%s" is not valid for logger "%s"'
                                     % (config_name, logger_name))
                self.api.set_active_logger_config(logger_name, config_name)

            ############################
            # configs <cruise_id>
            # elif command == 'configs':
            #   raise ValueError('format: configs')
            elif command.find('get_active_logger_configs') == 0:
                config_names = {logger_id: self.api.get_logger_config_name(logger_id)
                                for logger_id in self.api.get_loggers()}
                if len(config_names) > 0:
                    for logger_id, config_name in config_names.items():
                        print('%s: %s' % (logger_id, config_name))
                else:
                    print("No configs found!")

            ############################
            # status
            # elif command == 'status':
            #   raise ValueError('format: status')
            elif command.find('get_status') == 0:
                (status_cmd) = command.split(maxsplit=1)
                status_dict = self.api.get_status()
                print('%s' % pprint.pformat(status_dict))

            ############################
            # status_since
            elif command == 'get_status_since':
                raise ValueError('format: get_status_since <timestamp>')
            elif command.find('get_status_since ') == 0:
                (status_cmd, since_timestamp) = command.split(maxsplit=1)
                status_dict = self.api.get_status(float(since_timestamp))
                print('%s' % pprint.pformat(status_dict))

            ############################
            # server_log
            elif command == 'get_server_log':
                server_log = self.api.get_message_log(source=SOURCE_NAME)
                print('%s' % pprint.pformat(server_log))

            ############################
            # server_log timestamp
            elif command.find('get_server_log') == 0:
                (log_cmd, since_timestamp) = command.split(maxsplit=1)
                server_log = self.api.get_message_log(source=SOURCE_NAME, user=None,
                                                      log_level=self.api.DEBUG,
                                                      since_timestamp=float(since_timestamp))
                print('%s' % pprint.pformat(server_log))

            ############################
            # Quit gracefully
            elif command == 'quit':
                logging.info('Got quit command')
                self.quit()

            ############################
            elif command == 'help':
                self.show_commands()

            ############################
            else:
                print('Got unknown command: "{}"'.format(command))
                print('Type "help" for help')

        except ValueError as e:
            logging.error('%s', e)
        finally:
            self.api.message_log(source=SOURCE_NAME,
                                 user='(%s@%s)' % (USER, HOSTNAME),
                                 log_level=self.api.INFO,
                                 message='command: ' + command)


################################################################################
if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--database', dest='database', action='store',
                        choices=['memory', 'django', 'sqlite'],
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
    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
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
    elif args.database == 'sqlite':
        from server.sqlite_server_api import SQLiteServerAPI
        api = SQLiteServerAPI()
    else:
        raise ValueError('Illegal arg for --database: "%s"' % args.database)
    command_line_reader = ServerAPICommandLine(api)
    command_line_reader.run()
