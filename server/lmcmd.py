#! /usr/bin/env python3
"""
A command line tool for interacting with the LoggerManager and database. If called
with no arguments other than the optional database specification, it starts an
iterative command line interface. If arguments are present, it treats them as a
an OpenRVDAS command line command, executes it, them, then exits.

Within the iterative command line interface, you can type 'help' to see
available commands, and use arrow keys to navigate command history.

Args:
    --database
        Either 'django' or 'sqlite'; which database to connect to for OpenRVDAS
        state. If not specified, defaults to 'django'.
    -v
        If specified, increase verbosity of diagnostics from 'warning'
        to 'info'. If repeated, increase to 'debug'.

Usage:
    server/lmcmd.py
        Start a command line reader that reads/writes the default Django
        database used by OpenRVDAS.

    server/lmcmd.py help
        Print available interface commands and exit.

    server/lcmd.py get_active_mode
        Connect to default (django) database and run the 'get_active_mode'
        command.
"""
import argparse
import atexit
import logging
import os
import readline
import sys

from os.path import dirname, realpath

# Add the openrvdas components onto sys.path
sys.path.append(dirname(dirname(realpath(__file__))))
from logger.utils.stderr_logging import DEFAULT_LOGGING_FORMAT   # noqa: E402
from server.server_api_command_line import ServerAPICommandLine  # noqa: E402

################################################################################
if __name__ == '__main__':  # noqa: C901
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', dest='database', action='store',
                        choices=['django', 'sqlite'],
                        default='django', help='Which backing store database '
                        'to connect to')

    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')

    # Everything else on the command line
    parser.add_argument('remainder', nargs='*')
    args = parser.parse_args()

    ############################
    # Set up logging first
    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    log_level = LOG_LEVELS[min(args.verbosity, max(LOG_LEVELS))]
    logging.basicConfig(format=DEFAULT_LOGGING_FORMAT, level=log_level)
    parser = argparse.ArgumentParser()

    ############################
    # Instantiate API - which database is our backing store?
    if args.database == 'django':
        from django_gui.django_server_api import DjangoServerAPI
        api = DjangoServerAPI()
    elif args.database == 'sqlite':
        from server.sqlite_server_api import SQLiteServerAPI
        api = SQLiteServerAPI()
    else:
        raise ValueError('Illegal arg for --database: "%s"' % args.database)

    ############################
    # Set up command line interface to get commands. Start by
    # reading history file, if one exists, to get previous commands.
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
    command = ' '.join(args.remainder)

    ############################
    # Did they give us any additional args on command line? If so
    # execute them and exit. Otherwise fire up iterative reading
    # of commands.
    if command:
        command_line_reader.process_command(command)
        readline.add_history(command)
    else:
        command_line_reader.run()
