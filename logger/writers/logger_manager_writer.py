#!/usr/bin/env python3
"""
Writer that sends records it receives to the LoggerManager as commands. Can
be used in conjunction with GeofenceTransform for automatically switching
modes when entering/exiting an EEZ, or with a QCFilterTransform to turn off
loggers when conditions are violated.

Multiple commands may be sent in a single record by separating them with
semicolons.

In addition to the normally-accepted LoggerManager commands, an additional
one: "sleep N" is recognized, which will pause the writer N seconds before
writing the subsequent command. This allows time, if needed, for the effects
of prior commands to settle.

Sample logger that switches modes when entering/exiting EEZ:
```
# Read the latest lat/lon from the Cached Data Server
readers:
  class: CachedDataReader
  kwargs:
    data_server: localhost:8766
    subscription:
      fields:
        s330Latitude:
          seconds: 0
        s330Longitude:
          seconds: 0
# Look for lat/lon values in the DASRecords and emit appropriate commands
# when entering/leaving EEZ. Note that EEZ files in GML format can be
# downloaded from https://marineregions.org/eezsearch.php.
transforms:
  - class: GeofenceTransform
    module: loggers.transforms.geofence_transform
    kwargs:
      latitude_field_name: s330Latitude,
      longitude_field_name: s330Longitude
      boundary_file_name: /tmp/eez.gml
      leaving_boundary_message: set_active_mode write+influx
      entering_boundary_message: set_active_mode no_write+influx
# Send the messages that we get from geofence to the LoggerManager
writers:
  - class: LoggerManagerWriter
    module: logger.writers.logger_manager_writer
    kwargs:
      database: django
      allowed_prefixes:
        - 'set_active_mode '
        - 'sleep '
```
"""
import logging
import sys
import time

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.writers.writer import Writer  # noqa: E402
from server.server_api_command_line import ServerAPICommandLine  # noqa: E402


class LoggerManagerWriter(Writer):
    """Write received text records to the LoggerManager."""

    def __init__(self, database=None, api=None, allowed_prefixes=[]):
        """Write received text records as commands to the LoggerManager.
        ```
        database
                String indicating which database the LoggerManager is using: django,
                sqlite, memory. Either this or 'api', but not both, must be specified.

        api
                An instance of server_api.ServerAPI to use to communicate with the
                LoggerManager. Either this or 'database', but not both, must be specified.

        allowed_prefixes
                Optional list of strings. If specified, only records whose prefixes match
                something in this list will be passed on as commands.

        See server/server_api_command_line.py for recognized commands.

        Multiple commands may be sent in a single record by separating them with
        semicolons.

        In addition to the normally-accepted LoggerManager commands, an additional
        one: "sleep N" is recognized, which will pause the writer N seconds before
        writing the subsequent command. This allows time, if needed, for the effects
        of prior commands to settle.
        ```
        """
        if database and api:
            raise ValueError(f'Must specify either "database" or "api" but not both.')

        # If database specified, create appropriate api instance
        if database:
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

        # If not database, we'd better have an api specified
        elif not api:
            raise ValueError(f'Must specify one of "database" or "api".')

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

        # If there are semicolons, split into list and process sequentially
        if record.find(';') > -1:
            for single_record in record.split(';'):
                self.write(single_record)
            return

        # Can we find our command in any of the allowed prefixes?
        approved = True in [record.find(prefix) == 0 for prefix in self.allowed_prefixes]
        if self.allowed_prefixes and not approved:
            logging.error(f'Command does not match any allowed prefixes: "{record}"')

        # If it's our special "sleep" command
        elif record.find('sleep') == 0:
            try:
                cmd, interval_str = record.split(' ')
                interval = float(interval_str)
            except ValueError:
                logging.error(f'Could not parse command into "sleep [seconds]": {record}')
                return
            logging.info(f'Sleeping {interval} seconds')
            time.sleep(interval)

        else:
            logging.info(f'Writing command: {record}')
            self.command_parser.process_command(record)
