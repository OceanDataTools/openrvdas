#!/usr/bin/env python3
"""API implementation for interacting with a SQLite3 data store,
   by Kevin Pedigo, based on in_memory_server_api.py

   See api_tool.py for a simple script that exercises this class.
   See also server/server_api.py for full documentation of the API.
"""

import logging
import pprint
import sys
import sqlite3
import os
import yaml
import gzip
from datetime import datetime

from os.path import dirname, realpath
import time
sys.path.append(dirname(dirname(realpath(__file__))))

from server.server_api import ServerAPI  # noqa: E402

DEFAULT_MAX_TRIES = 3
ID_SEPARATOR = ':'

# Not a runtime option because the API doesn't have any
DATABASE_BACKUPS = True
DATABASE_COMPRESS = True

# Default location of SQLite database to use/create
DIR_PATH = os.path.dirname(__file__)
DEFAULT_DATABASE_PATH = os.path.join(DIR_PATH, 'openrvdas.sql')

# Effectively "time zero" for POSIX systems.
EPOCH_TIME_ZERO = '1970-01-01 00:00:00.000000'

########################################################################
# Let's trust SQLite and forget about thread locking.
# https://www.sqlite.org/lockingv3.html
# https://www.sqlite.org/threadsafe.html
# SQLITE3, by default, when built from source, builds in serialized mode
# (can be safely used by multiple threads without restriction)
# All distros tested are good.  To test yours:
# strings `which sqlite3` | grep THREADSAFE (should = 1)

class SQLiteServerAPI(ServerAPI):
    ############################

    def __init__(self, database_path=DEFAULT_DATABASE_PATH,
                 no_create_database=False):
        """
        database_path  - If specified, the path to the SQLite database to use

        no_create_database - If True, and database does not exist, throw an error
                             rather than creating a new database.
        """
        super().__init__()

        # Where do we l
        self.database_path = database_path
        self.no_create_database = no_create_database

        self.config = {}
        self.callbacks = []
        self.status = []
        self.server_messages = []
        self.cx = None
        self.timestamp = self._get_database_timestamp()


    def _database_exists(self):
        """Return True if SQLite database at self.database_path exists,
        and can be read without errors."""
        read_only_database_path = ''.join(['file:', self.database_path, '?mode=ro'])
        try:
            cx = sqlite3.connect(read_only_database_path, uri=True)
        except sqlite3.OperationalError:
            return False
        except sqlite3.Error as err:
            # Some other error
            logging.error(f'Unknown SQLite database error on read: {err}')
            return False
        return True

    def _create_database(self):
        """Try to create the database."""
        logging.debug(f'Creating SQLite database "{self.database_path}"')
        cx = sqlite3.connect(self.database_path)
        cu = cx.cursor()
        cu.execute('CREATE TABLE Cruise (highlander integer primary key not null, config blob, [loaded_time] datetime, compressed integer)')
        cu.execute('CREATE TABLE lastupdate (highlander integer primary key not null, [timestamp] datetime)')
        cu.execute('CREATE TABLE logmessages (timestamp datetime primary key not null, loglevel integer, cruise text, source text, user text, message text)')

        # We need a time or we think the database is not initialized
        cu.execute('INSERT INTO lastupdate (highlander, timestamp) VALUES (1, CURRENT_TIMESTAMP);')

        # Close, or not necessarily executed?
        cx.close()

    #############################
    # API methods below are used in querying/modifying the API for the
    # record of the running state of loggers.
    ############################
    def _get_connection(self):
        """ Return SQLite connection or get one """

        def dict_factory(cursor, row):
            """ Factory method for sqlite row as dictionary """
            d = {}
            for idx, col in enumerate(cursor.description):
                d[col[0]] = row[idx]
            return d

        # Return cached connection if it exists
        if self.cx is not None:
            return self.cx

        # Otherwise establish a connection to database
        if not self._database_exists():
            if self.no_create_database:
                raise OperationalError(f'No database "{self.database_path}" found, '
                                       'and flag "no_create_database" is set.')
            # Otherwise, create the missing database
            self._create_database()

        # Open the database for use
        try:
            cx = sqlite3.connect(self.database_path,
                                 check_same_thread=False,
                                 detect_types=sqlite3.PARSE_DECLTYPES)
        except sqlite3.Error as err:
            # Some other error
            logging.error(f'SQLite database error: {err}')
            raise err

        # Database exists and is now open
        cx.row_factory = dict_factory
        cx.isolation_level = None
        # cx.execute('PRAGMA ... etc...');
        # See if database is initialized
        try:
            cx.execute('SELECT timestamp from lastupdate')
        except sqlite3.OperationalError:
            # Database or table missing
            logging.error('System error: SQLite database exists but is not initialized!')
            raise sqlite3.OperationError
        except sqlite3.Error as err:
            # Some other error
            logging.error(f'SQLite database error: {err}')
            raise err
        else:
            self.cx = cx
            return self.cx

    ##################################################################
    def _sql_query(self, query, *args):
        """ Query the SQLite database.  Do NOT use this method
            for INSERT, UPDATE, or DELETE as it does not
            commit nor update the timestamp """

        cx = self._get_connection()
        try:
            res = cx.execute(query, args)
            rows = res.fetchall()
            return rows
        except sqlite3.OperationalError:
            # No such table.  We should be logging this.
            logging.error('System error: SQLite database exists but has no tables?')
            return None
        except sqlite3.Error as err:
            logging.error(f'SQLite database error: {err}')
            raise err

    ##################################################################
    def _sql_cmd(self, query, *args):
        """ Execute a SQL command that modifies the database """

        # NOTE(kped):  Consider not using the cached connection
        # in this function to help avoid possible threading
        # concurrency issues.
        cx = self._get_connection()
        try:
            res = cx.execute(query, args)
            rows = res.fetchall()
            # Update the database timestamp
            Q = 'INSERT OR REPLACE INTO lastupdate VALUES (1, ?)'
            now = datetime.utcnow()
            cx.execute(Q, (now,))
            cx.commit()
            # Note:  If using WAL, checkpoint
            return rows
        except sqlite3.OperationalError:
            # No such table
            logging.error(f'No such SQLite table for query: {query}')
            raise sqlite3.OperationalError
        except sqlite3.Error as err:
            logging.error(f'SQLite database error: {err}')
            raise err

    ##################################################################
    def _save_config(self):
        """Save our config object to the database"""

        Q = 'INSERT OR REPLACE INTO cruise \
             (highlander, config, compressed) \
             VALUES (1, ?, ?)'

        try:
            ydump = yaml.dump(self.config, sort_keys=False)
            logging.debug(f'YAML dump: "{ydump}"')
            conf = bytes(ydump, 'utf-8')
            logging.debug(f'YAML conf: "{conf}"')
            if DATABASE_COMPRESS:
                conf = gzip.compress(conf)
            self._sql_cmd(Q, conf, DATABASE_COMPRESS)
            cx = self._get_connection()
            # VACUUM takes a millisecond or so, but keeps the database
            # size small, which speeds us back up.
            cx.execute('VACUUM',)
        except Exception as err:
            logging.warn(f'Failed to save SQLite database: {err}')
            raise err
        else:
            # logging.info('Database save successful')
            pass

    ##################################################################
    def _get_database_timestamp(self):
        """Get the timestamp from the sqlite database"""

        Q = 'SELECT timestamp from lastupdate'
        cx = self._get_connection()
        try:
            res = cx.execute(Q)
            row = res.fetchone()
            if  row:
                return row['timestamp']

            # If no timestamp row, return string for 'time zero'
            return EPOCH_TIME_ZERO

        except sqlite3.OperationalError as err:
            # No such table
            logging.error('System error: SQLite database exists but is not initialized!')
            raise err
        except sqlite3.Error as err:
            logging.error(f'Unhandled SQLite database error: {err}')
            raise err

    ##################################################################
    def _do_we_need_to_reload(self):
        """ Check database timestamp and reload config if needed """

        db_timestamp = self._get_database_timestamp()
        if db_timestamp > self.timestamp or self.config == {}:
            Q = """SELECT
                       config, compressed
                   FROM
                       cruise
                   WHERE
                       highlander=1"""
            rows = self._sql_query(Q)
            row0 = None
            try:
                row0 = rows[0]
            except IndexError:
                return None

            if 'config' not in row0:
                return None
            conf = row0['config']

            # Wanted bzip, but build problems (probably install script)
            if row0.get('compressed', 0):
                conf = gzip.decompress(conf)

            # Wanted JSON, but datetime objects aren't JSON
            # serializable, so went with YAML.
            conf = yaml.load(conf, Loader=yaml.FullLoader)
            if 'loggers' not in conf:
                return None

            self.timestamp = db_timestamp
            self.config = conf

    # For each of the get_* function, check if the timestamp
    # is newer than our current timestamp, pull config from
    # the database.
    ##################################################################
    def get_configuration(self):
        """" Return cruise config for specified cruise id. """

        self._do_we_need_to_reload()
        return self.config or None

    ############################
    def get_modes(self):
        """ Return list of modes defined for given cruise. """

        config = self.get_configuration()
        if not config:
            return None
        return list(config.get('modes', []))

    ############################
    def get_active_mode(self):
        """ Return cruise config for specified cruise id."""

        config = self.get_configuration()
        if not config:
            return None
        return config.get('active_mode', None)

    ############################
    def get_default_mode(self):
        """ Get the name of the default mode for the specified cruise
        from the. data store. """

        config = self.get_configuration()
        if not config:
            return None
        return config.get('default_mode', None)

    ############################
    def get_logger(self, logger):
        """Retrieve the logger spec for the specified logger id."""

        loggers = self.get_loggers()   # which calls self._get_configuration
        if logger not in loggers:
            raise ValueError(f'No logger "{logger}" found')
        return loggers.get(logger)

    ############################
    def get_loggers(self):
        """Get a dict of
            {logger_id:{'configs':[<name_1>,<name_2>,...],
            'active':<name>},...}
        for all loggers.
        """

        config = self.get_configuration()
        if not config:
            return {}

        if 'loggers' not in config:
            raise ValueError('No loggers found')
        logger_configs = config.get('loggers', None)
        if logger_configs is None:
            raise ValueError('No logger configurations found')

        # Fetch and insert the currently active config for each logger
        # Note that this only changes our copy, not the config itself
        for logger in logger_configs:
            if 'active' not in logger_configs[logger]:
                mode = self.get_logger_config_name(logger)
                logger_configs[logger]['active'] = mode
        return logger_configs

    ############################
    def get_logger_config(self, config_name):
        """Retrieve the config associated with the specified name."""

        config = self.get_configuration()
        if config is None:
            return {}
        logger_configs = config.get('configs', None)
        if logger_configs is None:
            raise ValueError('No "configs" section found')
        logger_config = logger_configs.get(config_name, None)
        if logger_config is None:
            raise ValueError(f'No logger config "{config_name}" in config')
        return logger_config

    ############################
    def get_logger_configs(self, mode=None):
        """Retrieve the configs associated with a cruise id and mode from the
        data store. If mode is omitted, retrieve configs associated with
        the cruise's current logger configs."""

        loggers = self.get_loggers()
        if not loggers:
            return None

        output = {}
        for logger in loggers:
            logger_config_name = self.get_logger_config_name(logger, mode)
            output[logger] = self.get_logger_config(logger_config_name)

        return output

    ############################
    def get_logger_config_name(self, logger_id, mode=None):
        """ Retrieve name of the config associated with the specified logger
        in the specified mode.  If mode is omitted, retrieve name of logger's
        current config. """

        config = self.get_configuration()
        if not config:
            return {}
        loggers = config.get('loggers', None)
        if loggers is None:
            raise ValueError('No loggers found in config')

        # No mode, so we want the active mode
        if mode is None:
            logger = loggers.get(logger_id, None)
            if logger is None:
                raise ValueError(f'Logger id {logger_id} has no mode!')
            conf_name = logger.get('active', None)
            if conf_name is not None:
                return conf_name

        # Mode given or no active conf, so get the default for this mode
        modes = config.get('modes')
        mode_configs = modes.get(mode, None)
        if mode_configs is None:
            raise ValueError(f'Requested mode {mode} is not defined')
        logger_config_name = mode_configs.get(logger_id, None)
        if logger_config_name is None:
            raise ValueError(f'Logger {logger_id} has no config defined in mode {mode}')
        return logger_config_name

    #############################
    def get_logger_config_names(self, logger_id):
        """ Retrieve list of config names that are valid for the
            specified logger .
        > api.get_logger_config_names('NBP1406', 'knud')
              ["off", "knud->net", "knud->net/file", "knud->net/file/db"]
        """
        logger = self.get_logger(logger_id)
        return logger.get('configs', [])

    ############################
    # Methods for manipulating the desired state via API to indicate
    # current mode and which loggers should be in which configs.
    ############################
    def set_active_mode(self, mode):
        """Set the current mode of the specified cruise in the data store."""

        config = self.get_configuration()
        modes = config.get('modes', None)
        if not modes:
            raise ValueError('Config has no modes')
        if mode not in modes:
            raise ValueError(f'Config has no mode "{mode}"')

        self.config['active_mode'] = mode

        # Update the API's working config's loggers
        # to match the new mode
        for logger, conf in modes[mode].items():
            self.config['loggers'][logger]['active'] = conf

        self._save_config()
        logging.info('Signaling update')
        self.signal_update()

    ############################
    def set_active_logger_config(self, logger, config_name):
        """Set specified logger to new config. NOTE: we have no way to check
        whether logger is compatible with config, so we rely on whoever is
        calling us to have made that determination."""

        # self.logger_config[logger] = config_name
        # NOTE: We can check that config_name is in logger[configs]
        self.config['loggers'][logger]['active'] = config_name
        self._save_config()
        logging.info('Signaling update')
        self.signal_update()

    ############################
    # Methods for feeding data from LoggerServer back into the API
    ############################
    def update_status(self, status):
        """Save/register the loggers' retrieved status report with the API."""
        self.status.append(((datetime.utcnow()), status))
        # NOTE(kped) Do we need to write this to the database?
        # logger_manager never calls this....

    ############################
    # Methods for getting status data from API
    ############################

    def get_status(self, since_timestamp=None):
        """Retrieve a dict of the most-recent status report from each
        logger. If since_timestamp is specified, retrieve all status reports
        since that time."""

        # Start by getting set of loggers for cruise. Store as
        # cruise_id:logger for ease of lookup.
        try:
            logger_set = set([logger
                              for logger in self.get_loggers()])
        except ValueError:
            logger_set = set()

        logging.debug(f'logger_set: {logger_set}')

        # Step backwards through status messages until we run out of
        # status messages or reach termination condition. If
        # since_timestamp==None, our termination is when we have a status
        # for each of our loggers. If since_timestamp is a number, our
        # termination is when we've grabbed all the statuses with a
        # timestamp greater than the specified number.
        status = {}

        status_index = len(self.status) - 1
        logging.debug(f'starting at status index {status_index}')
        while logger_set and status_index >= 0:
            # record is a dict of 'cruise_id:logger' : {fields}
            (timestamp, record) = self.status[status_index]
            logging.debug('%d: %f: %s',
                          status_index, timestamp, pprint.pformat(record))

            # If we've been given a numeric timestamp and we've stepped back
            # in time to or before that timestamp, we're done - break out.
            if since_timestamp is not None and timestamp <= since_timestamp:
                break

            # Otherwise, examine ids in this record to see if they're for
            # the cruise in question.
            for id, fields in record.items():
                # If id is cruise_id:logger that we're interested in, grab it.
                logging.debug(f'Is {id} in {logger_set}?')
                if id in logger_set:
                    if timestamp not in status:
                        status[timestamp] = {}
                    status[timestamp][id] = fields

                    # If since_timestamp==None, we only want the latest status
                    # for each logger. So once we've found it, remove the id
                    # from the logger_set we're lookings. We'll drop out of the
                    # loop when the set is empty.
                    if since_timestamp is None:
                        logger_set.discard(id)
            status_index -= 1

        return status

    ############################
    # Methods for storing/retrieving messages from servers/loggers/etc.
    ############################
    def message_log(self, source, user, log_level, message):
        """ Timestamp and store the passed message. """

        now = datetime.utcnow()
        self.server_messages.append((now, source, user,
                                     log_level, message))

        # Keep server_messages from over-eating memory
        while len(self.server_messages) > 1000:
            self.server_messages.pop(0)

        Q = 'INSERT INTO logmessages \
             (timestamp, loglevel, cruise, source, user, message) \
             VALUES(?, ?, ?, ?, ?, ?)'

        cruise = self.config.get('cruise', {})
        cruise_id = cruise.get('id', 'none')

        self._sql_cmd(Q, now, log_level, cruise_id, source, user, message)

    ############################
    def get_message_log(self, source=None, user=None, log_level=sys.maxsize,
                        since_timestamp=None):
        """Retrieve log messages from source at or above log_level since
        timestamp. If source is omitted, retrieve from all sources. If
        log_level is omitted, retrieve at all levels. If since_timestamp is
        omitted, only retrieve most recent message.
        """

        # NOTE:  Should we pull this from the database?
        #        No... if they want more history, look directly.
        index = len(self.server_messages) - 1
        messages = []
        while index >= 0:
            message = self.server_messages[index]
            (timestamp, mesg_source, mesg_user,
             mesg_log_level, mesg_message) = message
            # Have we gone back too far? If so, we're done.
            if since_timestamp is not None and timestamp <= since_timestamp:
                break

            if mesg_log_level < log_level:
                continue
            if user and not mesg_user == user:
                continue
            if source and not mesg_source == source:
                continue

            messages.insert(0, message)

            # Are we only looking for last message, and do we have a message?
            if since_timestamp is None and messages:
                break
            index -= 1

        return messages

    #############################
    # Save a copy before empyting out the database
    ##############################
    def _backup_database(self):
        """ Backup the database """

        config = self.get_configuration()
        if not config:
            logging.debug('No configuration to back up')
            return
        cruise = config.get('cruise', {})
        cruise_id = cruise.get('id', 'none')

        dt = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        ourpath = os.path.dirname(__file__)
        filename = f'openrvdas-{cruise_id}-{dt}.sql'
        dbfile = os.path.join(ourpath, filename)
        try:
            cx = self._get_connection()
            cx.execute('VACUUM INTO ?', (dbfile,))
        except Exception as err:
            logging.warn(f'Failed to backup SQLite database: {err}')
            pass

    #####################################
    def load_configuration(self, config):
        """Add a complete cruise configuration (id, modes, configs,
        default) to the data store."""

        # Loaded new config, (optionally) backup old one
        if DATABASE_BACKUPS:
            self._backup_database()

        self.config = config
        # self.config['loaded_time'] = datetime.utcnow().isoformat()
        self.config['loaded_time'] = datetime.utcnow()

        # Set cruise into default mode, if one is defined
        if 'default_mode' in config:
            active_mode = config['default_mode']
            self.set_active_mode(active_mode)
        else:
            logging.warn('Cruise has no default mode')
        # Why not send the entire config to the CDS?  Why
        # just *almost* all of it?  JSON issue?
        cruise = config.get('cruise', None)
        if cruise:
            for key in ['id', 'start', 'end']:
                if key not in self.config:
                    self.config[key] = cruise.get(key, None)
        self._save_config()
        self.signal_load()

    ###############################
    def delete_configuration(self):
        """Remove the specified cruise from the data store."""
        self.config = {}
        # self.logger_config = {}
        self.callbacks = []
        self.status = []
        self._save_config()

    ############################
    # Methods for manually constructing/modifying a cruise spec via API
    def add_mode(self, cruise_id, mode):
        logging.warn('Method "add_mode" not implemented')

    def delete_mode(self, cruise_id, mode):
        logging.warn('Method "delete_mode" not implemented')

    def add_logger(self, cruise_id, logger_id, logger_spec):
        logging.warn('Method "add_logger" not implemented')

    def delete_logger(self, cruise_id, logger_id):
        logging.warn('Method "delete_logger" not implemented')

    def add_config(self, cruise_id, config, config_spec):
        logging.warn('Method "add_config" not implemented')

    def add_config_to_logger(self, cruise_id, config, logger_id):
        logging.warn('Method "add_config_to_logger" not implemented')

    def add_config_to_mode(self, cruise_id, config, logger_id, mode):
        logging.warn('Method "add_config_to_mode" not implemented')

    def delete_config(self, cruise_id, config_id):
        logging.warn('Method "delete_config" not implemented')
