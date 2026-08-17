#! /usr/bin/env python3
"""Manage the loggers defined by an OpenRVDAS cruise definition.

LoggerManager is the central process-control component of OpenRVDAS. It
reads desired logger configurations from a ServerAPI-based data store
(in-memory, SQLite or Django), runs each logger configuration in its own
process via a LoggerRunner, restarts loggers that die unexpectedly, and
reports logger status to a CachedDataServer.

May be invoked from the command line as, e.g.
```
    server/logger_manager.py \
        --config test/NBP1406/NBP1406_cruise.yaml \
        --mode monitor \
        --start_data_server
```
which will load the specified cruise definition, set it to the specified
mode and start a command line console for issuing commands. Type "help"
at the console for a list of commands.

In production it is typically run via supervisord with a persistent
database backing it:
```
    server/logger_manager.py --database django --no-console \
        --data_server_websocket :8766
```
"""
import datetime
import getpass  # to get username
import logging
import multiprocessing
import os
import signal
import socket  # to get hostname
import threading
import time

# Imports for running CachedDataServer
from server.cached_data_server import CachedDataServer  # noqa: E402

from server.logger_runner import LoggerRunner  # noqa: E402
from server.server_api import ServerAPI  # noqa: E402
from logger.transforms.to_das_record_transform import ToDASRecordTransform  # noqa: E402
from logger.utils.stderr_logging import DEFAULT_LOGGING_FORMAT  # noqa: E402
from logger.utils.stderr_logging import StdErrLoggingHandler  # noqa: E402
from logger.utils.read_config import read_config, expand_cruise_definition  # noqa: E402

# For sending stderr to CachedDataServer
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.writers.cached_data_writer import CachedDataWriter  # noqa: E402
from logger.writers.composed_writer import ComposedWriter  # noqa: E402

try:
    from server.sqlite_server_api import SQLiteServerAPI  # noqa: E402
    SQLITE_API_DEFINED = True
except ImportError:
    SQLITE_API_DEFINED = False

DEFAULT_MAX_TRIES = 3
DEFAULT_MIN_UPTIME = 10

SOURCE_NAME = 'LoggerManager'
USER = getpass.getuser()
HOSTNAME = socket.gethostname()

DEFAULT_DATA_SERVER_WEBSOCKET = 'localhost:8766'

############################


def kill_handler(signum, frame):
    """Translate an external signal (such as we'd get from os.kill) into a
    KeyboardInterrupt, which will signal the start() loop to exit nicely."""
    raise KeyboardInterrupt('Received external kill signal')

################################################################################
################################################################################


class LoggerState:
    """Per-logger runtime state: the config a logger is supposed to be
    running, the LoggerRunner executing it, and the bookkeeping we need
    to decide when to restart it or give up on it as failed.
    """

    def __init__(self, config, runner):
        self.config = config
        self.runner = runner
        self.last_started = time.time()
        self.restart_count = 0

################################################################################
################################################################################


class LoggerManager:
    ############################
    def __init__(self,
                 api, data_server_websocket=None,
                 stderr_file_pattern='/var/log/openrvdas/{logger}.stderr',
                 max_tries=DEFAULT_MAX_TRIES, min_uptime=DEFAULT_MIN_UPTIME,
                 interval=0.5, logger_log_level=logging.WARNING):
        """Read desired logger configs from the data store and try to keep
        the loggers specified in those configs running.
        ```
        api - ServerAPI (or subclass) instance by which LoggerManager will get
              its data store updates

        data_server_websocket - cached data server host:port to which we are
              going to send our status updates.

        stderr_file_pattern - Pattern into which logger name will be
              interpolated to create the file path/name to which the
              logger's stderr will be written. E.g.
              '/var/log/openrvdas/{logger}.stderr' If
              data_server_websocket is defined, will also write logger
              stderr to it.

        max_tries - number of times to try restarting a dead logger config
              before giving up on it as failed. If zero, never stop retrying.

        min_uptime - how many seconds a logger must run to count as having
              been successfully started and reset its restart count.

        interval - number of seconds to sleep between checking/updating
              loggers

        logger_log_level - at what logging level our component loggers
              should operate.
        ```
        """
        # Set signal to catch SIGTERM and convert it into a
        # KeyboardInterrupt so we can shut things down gracefully.
        try:
            signal.signal(signal.SIGTERM, kill_handler)
        except ValueError:
            logging.warning('LoggerManager not running in main thread; '
                            'shutting down with Ctl-C may not work.')

        # api class must be subclass of ServerAPI
        if not issubclass(type(api), ServerAPI):
            raise ValueError('Passed api "%s" must be subclass of ServerAPI' % api)
        self.api = api

        # Data server to which we're going to send status updates and to
        # which our loggers should send their stderr.
        self.data_server_websocket = data_server_websocket
        if data_server_websocket:
            self.data_server_writer = CachedDataWriter(data_server_websocket)

            # Also send our own stderr to the data server so the console
            # can display it.
            cds_writer = ComposedWriter(
                transforms=ToDASRecordTransform(data_id='stderr',
                                                field_name='stderr:logger_manager'),
                writers=self.data_server_writer)
            logging.getLogger().addHandler(StdErrLoggingHandler(cds_writer))
        else:
            self.data_server_writer = None

        self.stderr_file_pattern = stderr_file_pattern
        self.max_tries = max_tries
        self.min_uptime = min_uptime
        self.interval = interval
        self.logger_log_level = logger_log_level

        # How our various loops and threads will know it's time to quit
        self.quit_flag = False

        # Where we store the latest cruise definition and status reports.
        self.cruise = None
        self.cruise_filename = None
        self.cruise_loaded_time = 0

        self.loggers = {}

        self.logger_status = None
        self.status_time = 0

        # Map from logger name to LoggerState, holding the config each
        # logger should be running, the LoggerRunner running it and its
        # restart bookkeeping. Guarded by config_lock.
        self.logger_states = {}
        self.config_lock = threading.Lock()

        self.active_mode = None  # which mode is active now?
        self.active_configs = None  # which configs are active now?

        # The threads we'll run in start()
        self.run_loggers_thread = None
        self.send_cruise_definition_thread = None

    ############################
    def start(self):
        """Start the threads that make up the LoggerManager operation:

        1. Loop to update configs from the API, check that the loggers
           are running what they should be (restarting any that have died
           unexpectedly), and send status reports to the cached data server.
        2. Loop to check whether the cruise definition has changed and, if
           so, send the updated definition to the cached data server.

        Start threads as daemons so that they'll automatically terminate
        if the main thread does.
        """
        logging.info('Starting LoggerManager')

        self.run_loggers_thread = threading.Thread(
            name='run_loggers_loop',
            target=self._run_loggers_loop, daemon=True)
        self.run_loggers_thread.start()

        self.send_cruise_definition_thread = threading.Thread(
            name='send_cruise_definition_loop',
            target=self._send_cruise_definition_loop, daemon=True)
        self.send_cruise_definition_thread.start()

    ############################
    def quit(self):
        """Exit the loops and shut down all loggers."""
        self.quit_flag = True
        with self.config_lock:
            for logger in list(self.logger_states):
                self._delete_logger(logger)

        # Give our data server writer a chance to deliver anything still
        # queued (e.g. the loggers' final stderr lines) before we exit.
        if self.data_server_writer:
            self.data_server_writer.close()

    ############################
    def update_configs(self):
        """Fetch the latest desired configs from the API and start/stop
        loggers as necessary to match them.

        Called periodically from _run_loggers_loop(), and also registered
        as a callback so the API can invoke it when it knows the active
        configs have changed. Search for the line:

          api.on_update(callback=logger_manager.update_configs)

        in this file to see where.
        """
        # Get new configs in dict {logger: config_spec}
        logger_configs = self.api.get_logger_configs()
        if logger_configs:
            self._apply_configs(logger_configs)

    ############################
    def _apply_configs(self, configs):
        """Receive a new map of {logger: config} and start/stop loggers as
        necessary to match it.
        """
        with self.config_lock:
            # If we're in the process of quitting, go home - a different
            # thread is already shutting things down.
            if self.quit_flag:
                return

            stale_loggers = set(self.logger_states) - set(configs)
            new_loggers = set(configs) - set(self.logger_states)
            other_loggers = set(self.logger_states) - stale_loggers - new_loggers

            logging.debug('Stale: %s', stale_loggers)
            logging.debug('New: %s', new_loggers)
            logging.debug('Other: %s', other_loggers)

            # Find and shut down loggers that don't exist in our new configs
            for logger in stale_loggers:
                logging.info('Shutting down logger %s.', logger)
                self._delete_logger(logger)

            # Add loggers that have first appeared in our new config and
            # start them up.
            for logger in new_loggers:
                new_config = configs[logger]
                logging.info('Starting new logger %s with %s.', logger,
                             new_config.get('name', 'no_name'))
                self._start_logger(logger, new_config)

            # For existing loggers, see whether their configs have
            # changed. If so, stop and restart with new config.
            for logger in other_loggers:
                new_config = configs[logger]
                old_config = self.logger_states[logger].config
                if new_config == old_config:
                    logging.debug('Config for %s unchanged.', logger)
                    continue

                logging.info('Updating %s from %s to %s', logger,
                             old_config.get('name', 'no_name'),
                             new_config.get('name', 'no_name'))
                self._delete_logger(logger)
                self._start_logger(logger, new_config)

            self.active_configs = configs

    ############################
    def _start_logger(self, logger, config):
        """Create and start a LoggerRunner for the passed config. ONLY CALL
        THIS WITH config_lock HELD, for thread safety."""
        config_name = config.get('name', logger + '_config')
        logging.info('Called start_logger for %s: %s', logger, config_name)

        stderr_filename = self.stderr_file_pattern.format(logger=logger)

        # The runner captures the logger's actual stderr (fd 2) via a pipe
        # and relays each line back to us; we forward them to the cached
        # data server over our own connection, so the (possibly dying)
        # logger process is never responsible for delivering its own
        # death message.
        def stderr_callback(line, logger=logger):
            self._forward_logger_stderr(logger, line)

        # The relay thread also tells us - via pipe EOF - when the process
        # has died, so we can restart it immediately instead of waiting
        # for the next polling check.
        def death_callback(runner, logger=logger):
            self._handle_logger_death(runner, logger)

        runner = LoggerRunner(config=config, name=logger,
                              stderr_filename=stderr_filename,
                              stderr_callback=stderr_callback,
                              death_callback=death_callback,
                              logger_log_level=self.logger_log_level)
        self.logger_states[logger] = LoggerState(config=config, runner=runner)
        runner.start()

    ############################
    def _delete_logger(self, logger):
        """Shut down the named logger and forget about it. ONLY CALL THIS
        WITH config_lock HELD, for thread safety."""
        state = self.logger_states.get(logger)
        if not state:
            logging.warning('Stale logger %s not found?!?', logger)
            return
        logging.info('Waiting for logger %s to complete', logger)
        state.runner.quit()
        del self.logger_states[logger]

    ############################
    def _check_loggers(self):
        """Polling safety net: check that all the loggers we ought to be
        running are running, and restart any that have died unexpectedly.
        The primary death signal is _handle_logger_death(), called by each
        runner's stderr relay thread when its pipe hits EOF; this loop
        catches anything that slips past it.
        """
        logging.debug('Checking loggers...')
        with self.config_lock:
            for logger, state in self.logger_states.items():
                self._consider_restart(logger, state)

    ############################
    def _consider_restart(self, logger, state):
        """If the passed logger is unexpectedly dead, restart it - unless it
        has died max_tries times without staying up at least min_uptime
        seconds, in which case declare it failed and stop trying. ONLY CALL
        THIS WITH config_lock HELD, for thread safety.
        """
        runner = state.runner
        if not runner.is_runnable():
            return
        if runner.is_alive():
            return
        if runner.is_failed():
            return

        # If we're here, runner is runnable, is not running, and hasn't
        # yet been labeled as a failed logger.
        logging.warning('%s unexpectedly dead.', logger)

        # How long was it up? If long enough, give it a clean slate.
        if time.time() - state.last_started < self.min_uptime:
            state.restart_count += 1
        else:
            state.restart_count = 0

        # If we've restarted too many times recently, declare the logger
        # failed and move on. max_tries of zero means never stop retrying.
        if self.max_tries and state.restart_count >= self.max_tries:
            runner.failed = True
            logging.warning('%s has failed %s times; not restarting',
                            logger, state.restart_count)
            return

        # If here, we're going to try restarting.
        logging.info('%s - restarting', logger)
        state.last_started = time.time()
        runner.start()

    ############################
    def _handle_logger_death(self, runner, logger):
        """Called - from the dead runner's stderr relay thread - when a
        logger process's stderr pipe hits EOF, i.e. the process has exited
        and its last words have been delivered. Restart it (or declare it
        failed) right away rather than waiting for the next polling check.
        """
        if self.quit_flag or runner.quit_flag:
            return  # deliberate shutdown, not a death

        # Acquire the lock with a timeout: a manager thread holding it may
        # be in runner.quit(), joining the very relay thread we're running
        # in. Re-checking the quit flags lets us bail out instead of
        # stalling that join.
        while not self.config_lock.acquire(timeout=0.5):
            if self.quit_flag or runner.quit_flag:
                return
        try:
            state = self.logger_states.get(logger)
            if not state or state.runner is not runner:
                return  # stale notification; logger was reconfigured
            self._consider_restart(logger, state)
        finally:
            self.config_lock.release()

    ############################
    def get_status(self):
        """Return a dict of the current config name and current run status of
        each logger in the form, e.g.:

        {'s330': {'config':'s330->net', 'status':'RUNNING'},
         'gyr1': {'config':'gyr1->file', 'status':'FAILED'},
        }

        Possible status are EXITED, RUNNING, FAILED and STARTING. EXITED
        is the status when a logger is not 'runnable' - e.g. the 'off'
        config. STARTING is used when a runner is runnable but is not
        running and is not FAILED - i.e. we haven't given up on it.
        """
        logger_status = {}
        with self.config_lock:
            for logger, state in self.logger_states.items():
                config_name = state.config.get('name', 'no name')

                if not state.runner.is_runnable():
                    status = 'EXITED'
                elif state.runner.is_alive():
                    status = 'RUNNING'
                elif state.runner.is_failed():
                    status = 'FAILED'
                else:
                    status = 'STARTING'
                logger_status[logger] = {'config': config_name, 'status': status}
        return logger_status

    ############################
    def _run_loggers_loop(self):
        """Main supervision loop: update configs from the API, restart any
        loggers that have died unexpectedly, and send status reports to the
        cached data server.
        """
        while not self.quit_flag:
            try:
                self.update_configs()
                self._check_loggers()
                self._send_status()
            except Exception as e:
                # Catch broadly: a transient API error (e.g. SQLAlchemy
                # NoResultFound when no cruise is loaded yet) must not kill
                # this thread; we recover on the next iteration. See
                # upstream #562.
                logging.warning('Error in logger update loop: %s', e)
            time.sleep(self.interval)

    ############################
    def _send_status(self):
        """Assemble logger status and cruise mode and send them to the
        cached data server.
        """
        logger_status = self.get_status()
        self.logger_status = logger_status
        self.status_time = time.time()
        self._write_record_to_data_server('status:logger_status', logger_status)

        # Now get and send cruise mode
        mode_map = {'active_mode': self.api.get_active_mode()}
        self._write_record_to_data_server('status:cruise_mode', mode_map)

    ############################
    def load_definition_from_api(self):
        """Fetch a new cruise definition from the API and build local maps.
        Then send an updated cruise definition to the console.

        Called from _send_cruise_definition_loop() when it notices a new
        definition has been loaded, and also registered as a callback so
        the API can invoke it when a new definition is loaded. Search for
        the line:

          api.on_load(callback=logger_manager.load_definition_from_api)

        in this file to see where.
        """
        logging.info('Fetching new cruise definitions from API')
        try:
            self.loggers = self.api.get_loggers()

            self.cruise = self.api.get_configuration()  # a Cruise object
            self.cruise_filename = self.cruise.get('config_filename')
            loaded_time = self.cruise.get('loaded_time')
            self.cruise_loaded_time = datetime.datetime.timestamp(loaded_time)
            self.active_mode = self.api.get_active_mode()

            # Send updated cruise definition to CDS for console to read.
            cruise_dict = {
                'cruise_id': self.cruise.get('id', ''),
                'filename': self.cruise_filename,
                'config_timestamp': self.cruise_loaded_time,
                'loggers': self.loggers,
                'modes': self.cruise.get('modes', {}),
                'active_mode': self.active_mode,
            }
            logging.info('Sending updated cruise definitions to CDS.')
            self._write_record_to_data_server(
                'status:cruise_definition', cruise_dict)
        except Exception as e:
            logging.info('Failed to update cruise definition: %s', e)

    ############################
    def _send_cruise_definition_loop(self):
        """Iteratively check whether the cruise definition in the data store
        (or its source file) has changed. If the file has changed, send a
        notification to the console so it can ask whether the user wants to
        reload. If the data store has a definition with a newer timestamp,
        rebuild our local maps and send the updated definition to the
        cached data server.
        """
        last_loaded_timestamp = 0

        while not self.quit_flag:
            try:
                self.cruise = self.api.get_configuration()  # a Cruise object
                if not self.cruise:
                    logging.info('No cruise definition found in API')
                    time.sleep(self.interval * 2)
                    continue
                self.cruise_filename = self.cruise.get('config_filename')
                loaded_time = self.cruise.get('loaded_time')
                self.cruise_loaded_time = datetime.datetime.timestamp(loaded_time)

                # Has cruise definition file changed since we loaded it? If so,
                # send a notification to console so it can ask if user wants to
                # reload.
                if self.cruise_filename:
                    try:
                        mtime = os.path.getmtime(self.cruise_filename)
                        if mtime > self.cruise_loaded_time:
                            logging.debug('Cruise file timestamp changed!')
                            self._write_record_to_data_server('status:file_update', mtime)
                    except FileNotFoundError:
                        logging.debug('Cruise file "%s" has disappeared?', self.cruise_filename)

                # Does database have a cruise definition with a newer timestamp?
                # Means user loaded/reloaded definition. Update our maps to
                # reflect the new values and send an updated cruise_definition
                # to the console.
                if self.cruise_loaded_time > last_loaded_timestamp:
                    last_loaded_timestamp = self.cruise_loaded_time
                    logging.info('New cruise definition detected - rebuilding maps.')
                    self.load_definition_from_api()

            except Exception as e:
                logging.warning('Error checking cruise definition: %s', e)

            # Whether or not we've sent an update, sleep
            time.sleep(self.interval * 2)

    ############################
    def _forward_logger_stderr(self, logger, line):
        """Receive one line of a logger's stderr from its LoggerRunner's
        relay thread and forward it to the cached data server. Lines arrive
        already formatted/timestamped by the logger process itself.
        """
        if self.data_server_writer:
            record = DASRecord(data_id='stderr',
                               fields={'stderr:logger:' + logger: line})
            self.data_server_writer.write(record)

    ############################
    def _write_record_to_data_server(self, field_name, record):
        """Format and label a record and send it to the cached data server.
        """
        if self.data_server_writer:
            das_record = DASRecord(fields={field_name: record})
            logging.debug('DASRecord: %s' % das_record)
            self.data_server_writer.write(das_record)
        else:
            logging.info('Update: %s: %s', field_name, record)

################################################################################


def run_data_server(data_server_websocket,
                    data_server_back_seconds, data_server_cleanup_interval,
                    data_server_interval):
    """Run a CachedDataServer (to be called as a separate process),
    accepting websocket connections to receive data to be cached and
    served.
    """
    # First get the port that we're going to run the data server on. Because
    # we're running it locally, it should only have a port, not a hostname.
    # We should try to handle it if they prefix with a ':', though.
    data_server_websocket = data_server_websocket or DEFAULT_DATA_SERVER_WEBSOCKET
    websocket_port = int(data_server_websocket.split(':')[-1])
    server = CachedDataServer(port=websocket_port, interval=data_server_interval)

    # The server will start serving in its own thread after
    # initialization, but we need to manually fire up the cleanup loop
    # if we want it. Maybe we should have this also run automatically in
    # its own thread after initialization?
    server.cleanup_loop()


################################################################################
if __name__ == '__main__':  # noqa: C901
    import argparse
    import atexit
    import readline

    from server.server_api_command_line import ServerAPICommandLine

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', dest='config', action='store',
                        help='Name of configuration file to load.')
    parser.add_argument('--mode', dest='mode', action='store', default=None,
                        help='Optional name of mode to start system in.')

    database_choices = ['memory', 'django', 'fastapi']
    if SQLITE_API_DEFINED:
        database_choices.append('sqlite')
    parser.add_argument('--database', dest='database', action='store',
                        choices=database_choices,
                        default='memory', help='What backing store database '
                        'to use.')

    parser.add_argument('--stderr_file_pattern', dest='stderr_file_pattern',
                        default='/var/log/openrvdas/{logger}.stderr',
                        help='Pattern into which logger name will be '
                        'interpolated to create the file path/name to which '
                        'the logger\'s stderr will be written. E.g. '
                        '\'/var/log/openrvdas/{logger}.stderr\'')

    # Arguments for cached data server
    parser.add_argument('--data_server_websocket', dest='data_server_websocket',
                        action='store', default=None,
                        help='Address at which to connect to cached data server '
                        'to send status updates.')
    parser.add_argument('--start_data_server', dest='start_data_server',
                        action='store_true', default=False,
                        help='Whether to start our own cached data server.')
    parser.add_argument('--data_server_back_seconds',
                        dest='data_server_back_seconds', action='store',
                        type=float, default=480,
                        help='Maximum number of seconds of old data to keep '
                        'for serving to new clients.')
    parser.add_argument('--data_server_cleanup_interval',
                        dest='data_server_cleanup_interval',
                        action='store', type=float, default=60,
                        help='How often to clean old data out of the cache.')
    parser.add_argument('--data_server_interval', dest='data_server_interval',
                        action='store', type=float, default=1,
                        help='How many seconds to sleep between successive '
                        'sends of data to clients.')

    parser.add_argument('--interval', dest='interval', action='store',
                        type=float, default=0.5,
                        help='How many seconds to sleep between logger checks.')
    parser.add_argument('--max_tries', dest='max_tries', action='store', type=int,
                        default=DEFAULT_MAX_TRIES,
                        help='Number of times to retry failed loggers. If '
                        'zero, then never stop retrying.')
    parser.add_argument('--min_uptime', dest='min_uptime', action='store',
                        type=float, default=DEFAULT_MIN_UPTIME,
                        help='How many seconds a logger must run to count as '
                        'having been successfully started and reset its '
                        'restart count.')

    parser.add_argument('--no-console', dest='no_console', default=False,
                        action='store_true', help='Run without a console '
                        'that reads commands from stdin.')

    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    parser.add_argument('-V', '--logger_verbosity', dest='logger_verbosity',
                        default=0, action='count',
                        help='Increase output verbosity of component loggers')
    args = parser.parse_args()

    # Set up logging first of all
    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}

    log_level = LOG_LEVELS[min(args.verbosity, max(LOG_LEVELS))]
    logging.basicConfig(format=DEFAULT_LOGGING_FORMAT, level=log_level)

    # What level do we want our component loggers to write?
    logger_log_level = LOG_LEVELS[min(args.logger_verbosity, max(LOG_LEVELS))]

    ############################
    # First off, start any servers we're supposed to be running
    logging.info('Preparing to start LoggerManager.')

    # If we're supposed to be running our own CachedDataServer, start it
    # here in its own daemon process (daemon so that it dies when we exit).
    if args.start_data_server:
        data_server_proc = multiprocessing.Process(
            name='openrvdas_data_server',
            target=run_data_server,
            args=(args.data_server_websocket,
                  args.data_server_back_seconds, args.data_server_cleanup_interval,
                  args.data_server_interval),
            daemon=True)
        data_server_proc.start()

    ############################
    # Instantiate API - are we using an in-memory store, SQLite or Django
    # database as our backing store? Do our imports conditionally, so
    # they don't actually have to have Django if they're not using it.
    if args.database == 'django':
        from django_gui.django_server_api import DjangoServerAPI
        api = DjangoServerAPI()
    elif args.database == 'memory':
        from server.in_memory_server_api import InMemoryServerAPI
        api = InMemoryServerAPI()
    elif args.database == 'sqlite':
        from server.sqlite_server_api import SQLiteServerAPI  # noqa F811
        api = SQLiteServerAPI()
    elif args.database == 'fastapi':
        from server.fastapi_server_api import FastAPIServerAPI  # noqa F811
        api = FastAPIServerAPI()
    else:
        raise ValueError('Illegal arg for --database: "%s"' % args.database)

    ############################
    # Create our LoggerManager
    logger_manager = LoggerManager(
        api=api,
        data_server_websocket=args.data_server_websocket,
        stderr_file_pattern=args.stderr_file_pattern,
        max_tries=args.max_tries,
        min_uptime=args.min_uptime,
        interval=args.interval,
        logger_log_level=logger_log_level)

    # When told to quit, shut down gracefully
    api.on_quit(callback=logger_manager.quit)

    # When an active config changes in the database, update our configs here
    api.on_update(callback=logger_manager.update_configs)

    # When new configs are loaded, update our maps and send the new
    # definition to the cached data server
    api.on_load(callback=logger_manager.load_definition_from_api)

    ############################
    # If they've given us an initial configuration, get and load it.
    if args.config:
        config = read_config(args.config)
        config = expand_cruise_definition(config)

        # Hacky bit: need to stash the config filename for posterity
        if 'cruise' not in config or config['cruise'] is None:
            config['cruise'] = {}

        config['cruise']['config_filename'] = args.config
        api.load_configuration(config)

        active_mode = args.mode or api.get_default_mode()
        api.set_active_mode(active_mode)
        api.message_log(source=SOURCE_NAME, user='(%s@%s)' % (USER, HOSTNAME),
                        log_level=api.INFO,
                        message='started with: %s, mode %s' %
                        (args.config, active_mode))

    ############################
    # Start all the various LoggerManager threads running
    logger_manager.start()

    try:
        # If no console, just wait for the logger supervision thread to
        # end as a signal that we're done.
        if args.no_console:
            logging.warning('--no-console specified; waiting for LoggerManager '
                            'to exit.')
            if logger_manager.run_loggers_thread:
                logger_manager.run_loggers_thread.join()
            else:
                logging.warning('LoggerManager has no run_loggers_thread? '
                                'Exiting...')
        else:
            # Create reader to read/process commands from stdin. Note: this
            # needs to be in main thread for Ctl-C termination to be properly
            # caught and processed, otherwise interrupts go to the wrong places.

            # Set up command line interface to get commands. Start by
            # reading history file, if one exists, to get past commands.
            hist_filename = '.openrvdas_logger_manager_history'
            hist_path = os.path.join(os.path.expanduser('~'), hist_filename)
            try:
                readline.read_history_file(hist_path)
                # default history len is -1 (infinite), which may grow unruly
                readline.set_history_length(1000)
            except (FileNotFoundError, PermissionError, OSError):
                pass
            atexit.register(readline.write_history_file, hist_path)

            command_line_reader = ServerAPICommandLine(api=api)
            command_line_reader.run()

    except KeyboardInterrupt:
        pass
    logging.debug('Done with logger_manager.py - exiting')

    # Shut down all the loggers we're running
    logger_manager.quit()
