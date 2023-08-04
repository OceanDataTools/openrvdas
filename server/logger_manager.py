#! /usr/bin/env python3
"""
"""
import datetime
import getpass  # to get username
import logging
import multiprocessing
import os
import signal
import socket  # to get hostname
import sys
import threading
import time

from importlib import reload
from os.path import dirname, realpath

# Add the openrvdas components onto sys.path
sys.path.append(dirname(dirname(realpath(__file__))))

# Imports for running CachedDataServer
from server.cached_data_server import CachedDataServer  # noqa: E402

from server.logger_supervisor import LoggerSupervisor  # noqa: E402
from server.server_api import ServerAPI  # noqa: E402
from logger.transforms.to_das_record_transform import ToDASRecordTransform  # noqa: E402
from logger.utils.stderr_logging import DEFAULT_LOGGING_FORMAT  # noqa: E402
from logger.utils.stderr_logging import StdErrLoggingHandler  # noqa: E402
from logger.utils.read_config import read_config  # noqa: E402

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

SOURCE_NAME = 'LoggerManager'
USER = getpass.getuser()
HOSTNAME = socket.gethostname()

DEFAULT_DATA_SERVER_WEBSOCKET = 'localhost:8766'

############################


def kill_handler(self, signum):
    """Translate an external signal (such as we'd get from os.kill) into a
    KeyboardInterrupt, which will signal the start() loop to exit nicely."""
    raise KeyboardInterrupt('Received external kill signal')

################################################################################
################################################################################


class LoggerManager:
    ############################
    def __init__(self,
                 api, supervisor, data_server_websocket=None,
                 stderr_file_pattern='/var/log/openrvdas/{logger}.stderr',
                 interval=0.25, log_level=logging.info, logger_log_level=logging.WARNING):
        """Read desired/current logger configs from Django DB and try to run the
        loggers specified in those configs.
        ```
        api - ServerAPI (or subclass) instance by which LoggerManager will get
              its data store updates

        supervisor - a LoggerSupervisor object to use to manage logger
              processes.

        data_server_websocket - cached data server host:port to which we are
              going to send our status updates.

        stderr_file_pattern - Pattern into which logger name will be
              interpolated to create the file path/name to which the
              logger's stderr will be written. E.g.
              '/var/log/openrvdas/{logger}.stderr' If
              data_server_websocket is defined, will write logger
              stderr to it.

        interval - number of seconds to sleep between checking/updating loggers

        log_level - LoggerManager's log level

        logger_log_level - At what logging level our component loggers
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
        self.supervisor = supervisor

        # Data server to which we're going to send status updates
        if data_server_websocket:
            self.data_server_writer = CachedDataWriter(data_server_websocket)
        else:
            self.data_server_writer = None

        self.stderr_file_pattern = stderr_file_pattern
        self.interval = interval
        self.logger_log_level = logger_log_level

        # Try to set up logging, right off the bat: reset logging to its
        # freshly-imported state and add handler that also sends logged
        # messages to the cached data server.
        reload(logging)
        logging.basicConfig(format=DEFAULT_LOGGING_FORMAT, level=log_level)

        if self.data_server_writer:
            cds_writer = ComposedWriter(
                transforms=ToDASRecordTransform(data_id='stderr',
                                                field_name='stderr:logger_manager'),
                writers=self.data_server_writer)
            logging.getLogger().addHandler(StdErrLoggingHandler(cds_writer))

        # How our various loops and threads will know it's time to quit
        self.quit_flag = False

        # Where we store the latest cruise definition and status reports.
        self.cruise = None
        self.cruise_filename = None
        self.cruise_loaded_time = 0

        self.loggers = {}
        self.config_to_logger = {}

        self.logger_status = None
        self.status_time = 0

        # We loop to check the logger status and pass it off to the cached
        # data server. Do this in a separate thread.
        self.check_logger_status_thread = None

        # We'll loop to check the API for updates to our desired
        # configs. Do this in a separate thread. Also keep track of
        # currently active configs so that we know when an update is
        # actually needed.
        self.update_configs_thread = None
        self.config_lock = threading.Lock()

        self.active_mode = None  # which mode is active now?
        self.active_configs = None  # which configs are active now?

    ############################
    def start(self):
        """Start the threads that make up the LoggerManager operation:

        1. Configuration update loop
        2. Loop to read logger stderr/status and either output it or
           transmit it to a cached data server

        Start threads as daemons so that they'll automatically terminate
        if the main thread does.
        """
        logging.info('Starting LoggerManager')

        # Check logger status in a separate thread. If we've got the
        # address of a data server websocket, send our updates to it.
        self.check_logger_status_loop_thread = threading.Thread(
            name='check_logger_status_loop',
            target=self._check_logger_status_loop, daemon=True)
        self.check_logger_status_loop_thread.start()

        # Update configs in a separate thread.
        self.update_configs_thread = threading.Thread(
            name='update_configs_loop',
            target=self._update_configs_loop, daemon=True)
        self.update_configs_thread.start()

        # Check logger status in a separate thread. If we've got the
        # address of a data server websocket, send our updates to it.
        self.send_cruise_definition_loop_thread = threading.Thread(
            name='send_cruise_definition_loop',
            target=self._send_cruise_definition_loop, daemon=True)
        self.send_cruise_definition_loop_thread.start()

    ############################
    def quit(self):
        """Exit the loop and shut down all loggers."""
        self.quit_flag = True

    ############################
    def _load_new_definition_from_api(self):
        """Fetch a new cruise definition from API and build local maps. Then
        send anupdated cruise definition to the console.
        """
        logging.info('Fetching new cruise definitions from API')
        try:
            with self.config_lock:
                self.loggers = self.api.get_loggers()
                self.config_to_logger = {}
                for logger, logger_configs in self.loggers.items():
                    # Map config_name->logger
                    for config in self.loggers[logger].get('configs', []):
                        self.config_to_logger[config] = logger

                # This is a redundant grab of data when we're called from
                # _send_cruise_definition_loop(), but we may also be called
                # from a callback when the API alerts us that something has
                # changed. So we need to re-grab self.cruise
                self.cruise = self.api.get_configuration()  # a Cruise object
                self.cruise_filename = self.cruise.get('config_filename', None)
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
        except (AttributeError, ValueError, TypeError) as e:
            logging.info('Failed to update cruise definition: %s', e)

    ############################
    def _check_logger_status_loop(self):
        """Grab logger status message from supervisor and send to cached data
        server via websocket. Also send cruise mode as separate message.
        """
        while not self.quit_flag:
            now = time.time()
            try:
                config_status = self.supervisor.get_status()
                with self.config_lock:
                    # Stash status, note time and send update
                    self.config_status = config_status
                    self.status_time = now
                self._write_record_to_data_server('status:logger_status', config_status)

                # Now get and send cruise mode
                mode_map = {'active_mode': self.api.get_active_mode()}
                self._write_record_to_data_server('status:cruise_mode', mode_map)
            except ValueError as e:
                logging.warning('Error while trying to send logger status: %s', e)
            time.sleep(self.interval)

    ############################
    def _update_configs_loop(self):
        """Iteratively check the API for updated configs and send them to the
        appropriate LoggerRunners.
        """
        while not self.quit_flag:
            self._update_configs()
            time.sleep(self.interval)

    ############################
    def _update_configs(self):
        """Get list of new (latest) configs. Send to logger supervisor to make
        any necessary changes.

        Note: we can't fold this into _update_configs_loop() because we may
        need to ask the api to call it independently as a callback when it
        notices that the config has changed. Search for the line:

          api.on_update(callback=logger_manager._update_configs)

        in this file to see where.
        """
        # First, grab a status update.
        # self.logger_status = self.supervisor.check_status()
        # self.status_time = time.time()
        with self.config_lock:
            # Get new configs in dict {logger:{'configs':[config_name,...]}}
            logger_configs = self.api.get_logger_configs()
            if logger_configs:
                supervisor.update_configs(logger_configs)
                self.active_configs = logger_configs

    ############################
    def _send_cruise_definition_loop(self):
        """Iteratively assemble information from DB about what loggers should
        exist and what states they *should* be in. We'll send this to the
        cached data server whenever it changes (or if it's been a while
        since we have).

        Also, if the logger or config names have changed, signal that we
        need to create a new config file for the supervisord process to
        use.

        Looks like:
          {'active_mode': 'log',
           'cruise_id': 'NBP1406',
           'loggers': {'PCOD': {'active': 'PCOD->file/net',
                                'configs': ['PCOD->off',
                                            'PCOD->net',
                                            'PCOD->file/net',
                                            'PCOD->file/net/db']},
                        next_logger: next_configs,
                        ...
                      },
           'modes': ['off', 'monitor', 'log', 'log+db']
          }

        """
        last_loaded_timestamp = 0

        while not self.quit_flag:
            try:
                self.cruise = self.api.get_configuration()  # a Cruise object
                if not self.cruise:
                    logging.info('No cruise definition found in API')
                    time.sleep(self.interval * 2)
                    continue
                self.cruise_filename = self.cruise.get('config_filename', None)
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
                    self._load_new_definition_from_api()

            except KeyboardInterrupt:  # (AttributeError, ValueError, TypeError):
                logging.warning('No cruise definition found in API')

            # Whether or not we've sent an update, sleep
            time.sleep(self.interval * 2)

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

    database_choices = ['memory', 'django']
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
                        help='Number of times to retry failed loggers.')

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
    # If we do have a data server, add a handler that will echo all
    # logger_manager stderr output to it
    if args.data_server_websocket:
        stderr_writer = ComposedWriter(
            transforms=ToDASRecordTransform(field_name='stderr:logger_manager'),
            writers=[CachedDataWriter(data_server=args.data_server_websocket)])
        logging.getLogger().addHandler(StdErrLoggingHandler(stderr_writer,
                                                            parse_to_json=True))

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

    # Now that API is defined, tack on one more logging handler: one
    # that passes messages to API.
    # TODO: decide if we even need this. Disabled for now
    # logging.getLogger().addHandler(WriteToAPILoggingHandler(api))

    ############################
    # Create our logger supervisor.
    supervisor = LoggerSupervisor(
        configs=None,
        stderr_file_pattern=args.stderr_file_pattern,
        stderr_data_server=args.data_server_websocket,
        max_tries=args.max_tries,
        interval=args.interval,
        logger_log_level=logger_log_level)

    ############################
    # Create our LoggerManager
    logger_manager = LoggerManager(
        api=api, supervisor=supervisor,
        data_server_websocket=args.data_server_websocket,
        stderr_file_pattern=args.stderr_file_pattern,
        interval=args.interval,
        log_level=log_level,
        logger_log_level=logger_log_level)

    # When told to quit, shut down gracefully
    api.on_quit(callback=logger_manager.quit)
    api.on_quit(callback=supervisor.quit)

    # When an active config changes in the database, update our configs here
    api.on_update(callback=logger_manager._update_configs)

    # When new configs are loaded, update our file of config processes
    api.on_load(callback=logger_manager._load_new_definition_from_api)

    ############################
    # Start all the various LoggerManager threads running
    logger_manager.start()

    ############################
    # If they've given us an initial configuration, get and load it.
    if args.config:
        config = read_config(args.config)

        # Hacky bit: need to stash the config filename for posterity
        if 'cruise' in config:
            config['cruise']['config_filename'] = args.config
        api.load_configuration(config)

        active_mode = args.mode or api.get_default_mode()
        api.set_active_mode(active_mode)
        api.message_log(source=SOURCE_NAME, user='(%s@%s)' % (USER, HOSTNAME),
                        log_level=api.INFO,
                        message='started with: %s, mode %s' %
                        (args.config, active_mode))

    try:
        # If no console, just wait for the configuration update thread to
        # end as a signal that we're done.
        if args.no_console:
            logging.warning('--no-console specified; waiting for LoggerManager '
                            'to exit.')
            if logger_manager.update_configs_thread:
                logger_manager.update_configs_thread.join()
            else:
                logging.warning('LoggerManager has no update_configs_thread? '
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

    # Ask our SupervisorConnector to shutdown.
    if supervisor:
        supervisor.quit()
