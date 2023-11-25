#!/usr/bin/env python3

import logging
import os.path
import sys
import math

from datetime import datetime, timedelta, timezone

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.timestamp import time_str, DATE_FORMAT  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402
from server.server_api_command_line import ServerAPICommandLine

class LoggerManagerWriter(Writer):
    """Write received text records to the LoggerManager."""

    def __init__(self, database='django', allowed_prefixes=[]):
        """Write received text records as commands to the LoggerManager.
        ```
        database
                Which database the LoggerManager is using: django, sqlite, memory

        allowed_prefixes
                List of strings. Only records whose prefixes match something in this
                list will be passed on as commands.

        See server/server_api_command_line.py for recognized commands.

        In addition to the normally-accepted LoggerManager commands, an additional
        one: "sleep N" is recognized, which will pause the writer N seconds before
        writing the subsequent command. This allows time, if needed, for the effects
        of prior commands to settle.
        ```
        """
        if database == 'django':
            from django_gui.django_server_api import DjangoServerAPI
            api = DjangoServerAPI()
        elif database == 'memory':
            from server.in_memory_server_api import InMemoryServerAPI
            api = InMemoryServerAPI()
        elif database == 'sqlite':
            from server.sqlite_server_api import SQLiteServerAPI
            api = SQLiteServerAPI()
        else:
            raise ValueError(f'Parameter "database" must be one of [django, memory, sqlite], '
                             f'found "{database}"')
        self.command_parser = ServerAPICommandLine(api=api)

        if not type(allowed_prefixes) is list:
            raise ValueError(f'Parameter "allowed_prefixes" must be a list of strings, '
                             f'found "{allowed_prefixes}"')
        self.allowed_prefixes = allowed_prefixes

    ############################
    def write(self, record):
        """ Write out record, appending a newline at end."""
        if record is None:
            return

        # If we've got a list, assume it's a list of records. Recurse,
        # calling write() on each of the list elements in order.
        if isinstance(record, list):
            for single_record in record:
                self.write(single_record)
            return

        # Complain and go home if not string
        if type(record) is not str:
            logging.warning(f'Received non-string command for LoggerManager '
                            f'(type {type(record)}): "{record}"')
            return

        # Can we find our command in any of the allowed prefixes?
        approved = True in [record.find(prefix) for prefix in self.allowed_prefixes]

        if not approved:
            logging.error(f'Command does not match any allowed prefixes: "{record}"')

        # If it's our special "sleep" command
        elif record.find('sleep') == 0:
            try:
                cmd, interval_str = record.split(' ')
                interval = float(interval_str)
            except:
                logging.error(f'Could not parse command into "sleep [seconds]": {record}')
                return
            logging.info(f'Sleeping {interval} seconds')
            time.sleep(interval)

        else:
            logging.info(f'Writing command: {record}')
            self.command_parser(record)
