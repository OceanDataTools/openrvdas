#!/usr/bin/env python3
"""Command line interface for SQLiteServer API.
```
   sqlite_server/api_tool.py
```
and type "help" for list of valid commands.

Also see server/server_api.py for full documentation on the ServerAPI.
"""

import argparse
import atexit
import getpass  # to get username
import json
import yaml
import logging
import os
import pprint
import readline
import signal
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))
from logger.utils.read_config import read_config  # noqa: E402
from server.server_api import ServerAPI  # noqa: E402

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}

SOURCE_NAME = 'CommandLine'
USER = os.environ.get('SUDO_USER') or getpass.getuser()


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
            while not self.quit_requested:
                command = input('command? ')
                if command:
                    command = command.strip()
                    self.process_command(command)

        except (KeyboardInterrupt, EOFError):
            print()
            # logging.warning('ServerAPICommandLine.run() received Keyboard Interrupt')
        except Exception as e:
            logging.error(str(e))

        # Signal cleanup
        self.quit()

    ############################
    def show_commands(self):
        """Print summary of commands we can send to API."""

        commands = [
            ('get_configuration',
             """Retrieve the currently running configuration"""),
            ('get_modes', 'Get list of all defined modes'),
            ('get_active_mode', 'Get currently active mode'),
            ('get_default_mode', 'Get config\'s default mode'),
            ('get_loggers', 'Get list of all defined loggers'),
            ('get_logger <logger_id>',
             """ Retrieve the logger spec for the specified logger id"""),
            ('get_logger_config <config_name>',
             """ Get the logger config associated with the specified name"""),
            ('get_logger_configs <mode>',
             """Retrieve the configs associatged with the given mode.
             If mode is ommited, return current configs."""),
            ('get_logger_config_name <logger_id> [mode]',
             """Get the name of the logger config associated with the
             specified logger in the specified mode.  If mode is
             omitted, get the config name associated with the
             currently active mode"""),
            ('get_logger_config_names <logger_id>',
             """ Get list of logger config names for the specified logger."""),
            ('set_active_mode <name of mode>', 'Set new current mode\n'),
            ('set_active_logger_config <logger name> <name of logger config>',
             'Set logger to named configuration\n'),
            ('get_status',
             'Print most recent status for each logger'),
            ('message_log <source user loglevel message>',
             """Timestamp and store the passed message"""),
            ('get_message_log <source user log_level since_timestamp>',
             """Retrieve log messages from source at or above log_level since
             timestamp. If source is omitted, retrieve from all sources. If
             log_level is omitted, retrieve at all levels. If
             since_timestamp is omitted, only retrieve most recent
             message."""),
            ('load_configuration <configuration file name>',
             """Load a new config from file and set to default mode"""),
            # delete_configuration
            # add_mode
            # delete_mode
            # add_logger
            # delete_logger
            # add_logger_config
            # add_logger_config_to_logger
            # add_logger_config_to_mode
            # delete_logger_config
            ('quit', 'Quit gracefully')
        ]
        print('Valid commands:')
        for command, desc in commands:
            print('  %s\n      %s' % (command, desc))

    #####################################################
    def get_configuration(self, *args):
        """ Get OpenRVDAS configuration from the data store. """

        config = self.api.get_configuration()
        text = str(config)
        jconfig = yaml.load(text, Loader=yaml.FullLoader)
        print(yaml.dump(jconfig, indent=2))
        pass

    #####################################################
    def get_modes(self, *args):
        """Get the list of modes from the data store.
        > api.get_modes()
            ["off", "port", "underway"] """

        modes = self.api.get_modes()
        if len(modes) > 0:
            print('Available Modes: %s' % (', '.join(modes)))
        else:
            print('Available Modes: n/a')

    #####################################################
    def get_active_mode(self, *args):
        """Get the currently active mode from the data store.
        > api.get_active_mode()
            "port"
        """

        mode = self.api.get_active_mode()
        print('Current mode: %s' % (mode))

    #####################################################
    def get_default_mode(self, *args):
        """Get the default mode from the data store.
        > api.get_default_mode()
            "off"
        """

        mode = self.api.get_default_mode()
        print('Default mode: %s' % (mode))

    #####################################################
    def get_loggers(self, *args):
        """Get the dict of {logger_id:logger_spec,...} from the data store.
        > api.get_loggers()
            {
              "knud": {"host": "knud.pi", "configs":...},
              "gyr1": {"configs":...}
            }
        """

        loggers = self.api.get_loggers()
        print('Loggers: ', json.dumps(loggers))

    #####################################################
    def get_logger(self, *args):
        """Retrieve the logger spec for the specified logger id.
        > api.get_logger('knud')
            {"name": "knud->net", "host_id": "knud.pi", "configs":...}
        """

        splits = "".join(args).split(' ')
        if len(splits) < 2:
            Q = 'format: get_logger <logger_name>'
            raise ValueError(Q)
        logger_name = splits[1]
        logger_modes = self.api.get_logger(logger_name)
        Q = "Modes for logger %s: %s" % \
            (logger_name, json.dumps(logger_modes))
        print(Q)

    #####################################################
    def get_logger_configs(self, *args):
        """Retrieve the configs associated with a mode from the data store.
        If mode is omitted, retrieve configs associated with the active mode.
        > api.get_logger_configs()
               {"knud": { config_spec },
                "gyr1": { config_spec }
               }
        """
        splits = "".join(args).split(' ')
        if len(splits) < 2:
            mode = None
        else:
            mode = splits[1]
        configs = self.api.get_logger_configs(mode)
        Q = "configs for mode %s: %s" % (mode, configs)
        print(Q)

    #####################################################
    def get_logger_config_name(self, *args):
        """Retrieve the name of the logger config associated with the
        specified logger in the specified mode. If mode is omitted,
        retrieve config name associated with the active mode.
        > api.get_logger_config_name('knud')
            knud->net
       """

        splits = "".join(args).split(' ')
        if len(splits) == 1:
            Q = 'format: get_logger_config_name <logger name> [optional mode]'
            raise ValueError(Q)
        if len(splits) < 3:
            mode = None
        else:
            mode = splits[2]
        logger_name = splits[1]
        config_name = self.api.get_logger_config_name(logger_name, mode)
        print("logger_config_name(%s, %s): " %
              (logger_name, mode), config_name)

    #####################################################
    def get_logger_config_names(self, *args):
        """Retrieve list of logger config names for the specified logger.
        > api.get_logger_config_names('knud')
            ["off", "knud->net", "knud->net/file", "knud->net/file/db"]
        """

        splits = "".join(args).split(' ')
        if len(splits) == 1:
            raise ValueError(
                'format: get_logger_config_names <logger_id>')
        logger_id = splits[1]
        print("get_logger_config_names(%s)" % logger_id)
        config_names = self.api.get_logger_config_names(logger_id)
        print("logger_config_names(%s) = " % logger_id, config_names)

    #####################################################
    def set_active_mode(self, *args):
        """Set the active mode for OpenRVDAS.
        > api.set_active_mode(port')
        """

        splits = "".join(args).split(' ')
        if len(splits) == 1:
            raise ValueError('format: set_active_mode <mode>')
        mode_name = splits[1]
        self.api.set_active_mode(mode_name)
        self.api.message_log(source=SOURCE_NAME,
                             user='(%s@localhost)' % USER,
                             log_level=self.api.INFO,
                             message='Change: ' + args)

    #####################################################
    def set_active_logger_config(self, *args):
        """Set the active logger config for the specified logger to
        the specific logger_config name.
        > api.set_active_logger_config('knud', 'knud->file/net/db')
        """

        splits = "".join(args).split(' ')
        if len(splits) < 3:
            Q = 'set_active_logger_config <logger_id> <logger config>'
            raise ValueError(Q)
        Q = 'Setting logger %s to config %s'
        logger_name = splits[1]
        config_name = splits[2]
        logging.info(Q, logger_name, config_name)
        # Is this a valid config for this logger?
        if config_name not in self.api.get_logger_config_names(logger_name):
            Q = 'Config "%s" is not valid for logger "%s"'
            raise ValueError(Q % (config_name, logger_name))
        self.api.set_active_logger_config(logger_name, config_name)
        self.api.message_log(source=SOURCE_NAME,
                             user='(%s@localhost)' % USER,
                             log_level=self.api.INFO,
                             message='Change: ' + args)
        pass

    #####################################################
    def get_status(self, *args):
        """ Print most recent status for each logger """

        status_dict = self.api.get_status()
        print('%s' % pprint.pformat(status_dict))

    #####################################################
    def _message_log(self, *args):
        """ Save message to the API datastore """

        # splits = "".join(args).split(' ')
        # How we gonna parse KWARGS?
        # toss in argparser here?
        pass

    #####################################################
    def get_message_log(self, *args):
        """ Get logged messages from the API """

        splits = "".join(args).split(' ')
        if len(splits) < 2:
            SOURCE_NAME = None
        else:
            SOURCE_NAME = splits[1]
        server_log = self.api.get_message_log(source=SOURCE_NAME)
        print('%s' % pprint.pformat(server_log))

    #####################################################
    def delete_configuration(self, *args):
        self.api.delete_configuration()
        pass

    #####################################################
    def get_logger_config(self, *args):
        """ get_logger_config <logger_id> """

        splits = "".join(args).split(' ')
        if len(splits) < 2:
            Q = 'get_logger_config <logger_id>'
            raise ValueError(Q)
        logger_id = splits[1]
        logger_config = self.api.get_logger_config(logger_id)
        print('Configs for %s: %s' % (logger_id, logger_config))

    #####################################################
    def load_configuration(self, *args):

        splits = "".join(args).split(' ')
        if len(splits) == 1:
            Q = ('format: load_configuration <config file name>')
            raise ValueError(Q)
        filename = splits[1]
        try:
            # Load the file to memory and parse to a dict. Add the name
            # of the file we've just loaded to the dict.
            config = read_config(filename)
            config['config_filename'] = filename
            print("config['config_filename'] = %s" % config['config_filename'], file=sys.stderr)

            self.api.load_configuration(config)
            default_mode = self.api.get_default_mode()
            if default_mode:
                self.api.set_active_mode(default_mode)
            self.api.message_log(source=SOURCE_NAME,
                                 user='(%s@localhost)' % USER,
                                 log_level=self.api.INFO,
                                 message='Change: ' + command)
        except FileNotFoundError:
            logging.error('Unable to find file "%s"', filename)
        except Exception as err:
            print("Exception in load_configuration: ", err, file=sys.stderr)

        # for key in self.api.__dict__.keys():
        #    print()
        #    print(key, " = ", self.api.__dict__[key])
        #    print()

    ############################
    def process_command(self, command):
        """Parse and execute the command string we've received."""

        # KPED hates massive if/else strings.  KPED *likes*
        # dispatch tables.
        dtable = {
            # In the order they're defined in server_api.py
            'get_configuration': self.get_configuration,
            'get_modes': self.get_modes,
            'get_active_mode': self.get_active_mode,
            'get_default_mode': self.get_default_mode,
            'get_loggers': self.get_loggers,
            'get_logger': self.get_logger,
            'get_logger_config': self.get_logger_config,
            'get_logger_configs': self.get_logger_configs,
            'get_logger_config_name': self.get_logger_config_name,
            'get_logger_config_names': self.get_logger_config_names,
            'set_active_mode': self.set_active_mode,
            'set_active_logger_config': self.set_active_logger_config,
            'get_status': self.get_status,
            # message_log
            'get_message_log': self.get_message_log,
            'load_configuration': self.load_configuration,
            ###################################################
            # The following are not implemented, but are
            # listed here in case somebody gets froggy some day
            # delete_configuration
            # add_mode
            # delete_mod
            # add_logger
            # delete_logger
            # add_logger_config
            # add_logger_config_to_logger
            # add_logger_config_to_mode
            # delete_logger_config
        }

        try:
            if not command:
                logging.info('Empty command received')
            else:
                splits = command.split()
                cmd = splits[0]
                if cmd in dtable:
                    try:
                        dtable[cmd](command)
                    except Exception as err:
                        print("Error in %s: %s" % (cmd, err))
                    return

            if False:
                pass

            ############################
            # Quit gracefully
            elif command == 'quit':
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
        except KeyboardInterrupt:
            pass
        finally:
            pass


# Seems like there should be some way to
# combine the help table, dispatch table, and
# this table.  Just nothing intuitive comes to mind.  Grrr....
vocab = [
    'get_configuration',
    'get_modes',
    'get_active_mode',
    'get_default_mode',
    'get_loggers',
    'get_logger',
    'get_logger_config',
    'get_logger_configs',
    'get_logger_config_name',
    'get_logger_config_names',
    'set_active_mode',
    'set_active_logger_config',
    'get_status',
    'message_log',
    'get_message_log',
    'load_configuration'
    # delete_configuration
    # add_mode
    # delete_mode
    # add_logger
    # delete_logger
    # add_logger_config
    # add_logger_config_to_logger
    # add_logger_config_to_mode
]


def readline_completer(text, state):
    results = [x for x in vocab if x.startswith(text)] + [None]
    return results[state]


################################################################################
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
                        description='Command line tool for this API')
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    parser.add_argument('-V', '--logger_verbosity', dest='logger_verbosity',
                        default=0, action='count',
                        help='Increase output verbosity of component loggers')
    parser.add_argument('remainder', nargs='*',
                        help='will be interpreted as a ServerAPI command')
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
    try:
        readline.parse_and_bind("tab: complete")
        readline.set_completer(readline_completer)
    except Exception as err:
        print("Error setting readline completion: ", err)
        pass
    atexit.register(readline.write_history_file, histpath)

    ############################
    # Instantiate API
    from sqlite_gui.sqlite_server_api import SQLiteServerAPI
    api = SQLiteServerAPI()
    command_line_reader = ServerAPICommandLine(api)
    command = ' '.join(args.remainder)

    if command:
        command_line_reader.process_command(command)
        readline.add_history(command)
    else:
        try:
            command_line_reader.run()
        except KeyboardInterrupt:
            pass
