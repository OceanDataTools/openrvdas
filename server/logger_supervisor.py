#! /usr/bin/env python3
"""
"""
import datetime
import getpass  # to get username
import json
import logging
import multiprocessing
import os
import pprint
import signal
import socket  # to get hostname
import subprocess
import sys
import tempfile
import threading
import time
import websockets

# For communicating with supervisord server
from xmlrpc.client import ServerProxy
from xmlrpc.client import Fault as XmlRpcFault
from xml.parsers.expat import ExpatError as XmlExpatError
from http.client import ResponseNotReady as ResponseNotReady
from http.client import CannotSendRequest as CannotSendRequest

from os.path import dirname, realpath

# Add the openrvdas components onto sys.path
sys.path.append(dirname(dirname(realpath(__file__))))

from logger.utils.read_config import read_config
from logger.writers.cached_data_writer import CachedDataWriter
from server.server_api import ServerAPI

# Imports for running CachedDataServer
from server.cached_data_server import CachedDataServer

from logger.utils.das_record import DASRecord
from logger.utils.stderr_logging import DEFAULT_LOGGING_FORMAT

DEFAULT_MAX_TRIES = 3

SOURCE_NAME = 'LoggerSupervisor'
USER = getpass.getuser()
HOSTNAME = socket.gethostname()

DEFAULT_SUPERVISOR_PORT = 8002
DEFAULT_SUPERVISOR_LOGFILE_DIR = '/var/log/openrvdas'

############################
def kill_handler(self, signum):
  """Translate an external signal (such as we'd get from os.kill) into a
  KeyboardInterrupt, which will signal the start() loop to exit nicely."""
  raise KeyboardInterrupt('Received external kill signal')

############################
# Templates used by SupervisorConnector to create config files

SUPERVISORD_TEMPLATE = """
; Auto-generated supervisord file - edits will be overwritten!

[unix_http_server]
file={supervisor_dir}/supervisor.sock   ; the path to the socket file
chmod=0770                 ; socket file mode (default 0700)
;chown={user}:{group}       ; socket file uid:gid owner
;username={user}           ; default is no username (open server)
;password={password}       ; default is no password (open server)

[inet_http_server]         ; inet (TCP) server disabled by default
port=localhost:{port}      ; ip_address:port specifier, *:port for all iface
;username={user}           ; default is no username (open server)
;password={password}       ; default is no password (open server)

[supervisord]
logfile={logfile_dir}/supervisord.log ; main log file; default $CWD/supervisord.log
logfile_maxbytes=50MB     ; max main logfile bytes b4 rotation; default 50MB
logfile_backups=10        ; # of main logfile backups; 0 means none, default 10
loglevel={log_level}      ; log level; default info; others: debug,warn,trace
pidfile={supervisor_dir}/supervisord.pid ; supervisord pidfile; default supervisord.pid
nodaemon=true      ; start in foreground if true; default false
minfds=1024        ; min. avail startup file descriptors; default 1024
minprocs=200       ; min. avail process descriptors;default 200
umask=022          ; process file creation umask; default 022
user={user}        ; setuid to this UNIX account at startup; recommended if root

; The rpcinterface:supervisor section must remain in the config file for
; RPC (supervisorctl/web interface) to work.  Additional interfaces may be
; added by defining them in separate [rpcinterface:x] sections.

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

; The supervisorctl section configures how supervisorctl will connect to
; supervisord.  configure it match the settings in either the unix_http_server
; or inet_http_server section.

[supervisorctl]
serverurl=unix:///{supervisor_dir}/supervisor.sock ; use a unix:// URL  for a unix socket
serverurl=http://localhost:{port} ; use an http:// url to specify an inet socket
;username={user}              ; should be same as in [*_http_server] if set
;password={password}          ; should be same as in [*_http_server] if set

[include]
files = {supervisor_dir}/supervisor.d/*.ini
"""

SUPERVISOR_LOGGER_TEMPLATE = """
[program:{config_name}]
command=logger/listener/listen.py --config_string '{config_json}' {log_v}
directory={directory}
autostart=false
autorestart={autorestart}
startsecs={startsecs}
startretries={startretries}
user={user}
stderr_logfile_maxbytes=50MB
stderr_logfile_backups=10
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
{comment_log}stderr_logfile={logfile_dir}/{logger}.err.log
{comment_log}stdout_logfile={logfile_dir}/{logger}.out.log
"""

################################################################################
################################################################################
class SupervisorConnector:
  ############################
  def __init__(self,
               start_supervisor=False,
               supervisor_logger_config_file=None,
               supervisor_port=DEFAULT_SUPERVISOR_PORT,
               supervisor_logfile_dir=DEFAULT_SUPERVISOR_LOGFILE_DIR,
               max_tries=DEFAULT_MAX_TRIES,
               log_level=logging.WARNING):
    """Connect to a supervisord process, or start our own to manage
    processes.  If starting our own, do so in a tempdir of our own
    creation that will go away when connector is destroyed.
    ```
    start_supervisor - Start local copy of supervisord, building its own
          config file in a temporary file.

    supervisor_logger_config - Location of file where supervisord should look
          for logger process definitions. Mutually exclusive with
          --start_supervisor flag.

    supervisor_port - Localhost port at which supervisor should serve.

    supervisor_logfile_dir - Directory where supevisord and logger
          stderr/stdout will be written.

    max_tries = Number of times a failed logger should be retried if it
          fails on startup.
    ```
    """
    self.supervisor_port = supervisor_port
    self.supervisor_logfile_dir = supervisor_logfile_dir
    self.max_tries = max_tries

    # Define this right at start, because if we shut down prematurely
    # during initialization, the destructor is going to look for it.
    self.supervisord_proc = None

    # If we're starting our own local copy of supervisor, create the
    # relevant config files in a temp directory.
    if start_supervisor:
      self.supervisor_dir = tempfile.TemporaryDirectory()
      supervisor_dirname = self.supervisor_dir.name

      supervisor_log_level = {logging.WARNING: 'warn',
                              logging.INFO: 'info',
                              logging.DEBUG: 'debug'}.get(log_level, 'warn')

      # Create the supervisor config file
      supervisor_config_filename = supervisor_dirname + '/supervisord.ini'
      config_args = {
        'supervisor_dir': supervisor_dirname,
        'logfile_dir': supervisor_logfile_dir,
        'port': supervisor_port,
        'user': getpass.getuser(),
        'group': getpass.getuser(),
        'password': 'NOT_USED',
        'log_level': supervisor_log_level,
      }
      supervisor_config_str = SUPERVISORD_TEMPLATE.format(**config_args)
      with open(supervisor_config_filename, 'w') as supervisor_config_file:
        supervisor_config_file.write(supervisor_config_str)

      # Create directory where logger.ini file will go
      os.mkdir(supervisor_dirname + '/supervisor.d')
      self.supervisor_logger_config_file = \
         supervisor_dirname + '/supervisor.d/loggers.ini'

      # Create an empty logger.ini file to prevent supervisor from
      # complaining that there are no matching .ini files when it
      # starts up. Petty, I know, but the warning could cause folks to
      # worry about the wrong thing if something else is amiss.
      open(self.supervisor_logger_config_file, 'a').close()

      # Make sure supervisord exists and is on path
      SUPERVISORD = 'supervisord'
      try:
        subprocess.check_output(['which', SUPERVISORD])
      except subprocess.CalledProcessError:
        logging.fatal('Supervisor executable "%s" not found', SUPERVISORD)
        sys.exit(1)

      # And start the local supervisord
      self.supervisord_proc = subprocess.Popen(
        ['/usr/bin/env', SUPERVISORD, '-n', '-c', supervisor_config_filename])

    # If not starting our own supervisor, stash pointer to where we
    # expect the existing supervisor to look for a logger config
    # file. If we call
    else:
      self.supervisor_logger_config_file = supervisor_logger_config_file

    # Now that the preliminaries are done, try to connect to server.
    self.supervisor_rpc = self._create_supervisor_connection()

    # Create a second connection that we will use to read logger
    # process stderr. We'll guard reads from this from stepping on
    # each other by means of a thread lock.
    self.read_stderr_rpc =  self._create_supervisor_connection()
    self.config_lock = threading.Lock()
    self.read_stderr_offset = {}  # how much of each stderr we've read

    # Finally, keep track of the configs that are currently active
    self._running_configs = set()

  ############################
  def _create_supervisor_connection(self):
    """Connect to server. If we fail, sleep a little and try again."""
    while True:
      supervisor_url = 'http://localhost:%d/RPC2' % self.supervisor_port
      logging.info('Connecting to supervisor at %s', supervisor_url)

      supervisor_rpc = ServerProxy(supervisor_url)
      try:
        supervisor_state = supervisor_rpc.supervisor.getState()
        if supervisor_state['statename'] == 'RUNNING':
          break

        logging.error('Supervisord is not running. State is "%s"',
                      supervisor_state['statename'])
      except ConnectionRefusedError:
        logging.info('Unable to connect to supervisord at %s', supervisor_url)
      time.sleep(5)
      logging.info('Retrying connection to %s', supervisor_url)

    # Return with our connection
    return supervisor_rpc

  ############################
  def __del__(self):
    self.shutdown()

  ############################
  def _clean_name(self, config_name):
    """Remove characters from a string that supervisord can't handle as
    a process name.
    """
    return config_name.replace('/', '+')

  ############################
  def start_configs(self, configs_to_start, group=None):
    """Ask supervisord to start the listed configs. Note that all logger
    configs are part of group 'logger', so we need to prefix all names
    with 'logger:' when talking to supervisord about them.

    configs_to_start - a list of config names that should be started.

    group - process group in which the configs were defined; will be
        prepended to config names.
    """
    configs = list(configs_to_start)  # so we can order results
    config_calls = []

    with self.config_lock:
      for config in configs:
        config = self._clean_name(config)  # get rid of objectionable characters
        if group:
          config = group + ':' + config
        config_calls.append({'methodName':'supervisor.startProcess',
                             'params':[config, False]})

      # Make calls in parallel and update set of currently-running configs
      results = self.supervisor_rpc.system.multicall(config_calls)
      self._running_configs |= configs_to_start

    # Let's see what the results are
    for i in range(len(results)):
      result = results[i]
      config = configs[i]
      if type(result) is dict:
        if result['faultCode'] == 60:
          logging.warning('Starting process %s, but already started', config)
        else:
          logging.warning('Starting process %s: %s', config,
                          result['faultString'])

  ############################
  def stop_configs(self, configs_to_stop, group=None):
    """Ask supervisord to stop the listed configs. Note that all logger
    configs are part of group 'logger', so we need to prefix all names
    with 'logger:' when talking to supervisord about them.

    configs_to_stop - a list of config names that should be stopped.

    group - process group in which the configs were defined; will be
        prepended to config names.
    """
    configs = list(configs_to_stop)  # so we can order results
    config_calls = []

    with self.config_lock:
      for config in configs:
        config = self._clean_name(config)  # get rid of objectionable characters
        if group:
          config = group + ':' + config
        config_calls.append({'methodName':'supervisor.stopProcess',
                             'params':[config, False]})

      # Make calls in parallel and update set of currently-running configs
      results = self.supervisor_rpc.system.multicall(config_calls)
      self._running_configs = self._running_configs - configs_to_stop

    # Let's see what the results are
    for i in range(len(results)):
      result = results[i]
      config = configs[i]
      if type(result) is dict:
        if result['faultCode'] == 60:
          logging.info('Stopping process %s, but already stopped', config)
        else:
          logging.info('Stopping process %s: %s', config, result['faultString'])

  ############################
  def running_configs(self):
    """Return set of currently-running configs."""
    return self._running_configs

  ############################
  def read_status(self):
    """Read the status of currently active configs

    loggers - dict mapping logger names->list of configs:

      {
        logger_1: {
          'configs': [
            'logger_1->off',
            'logger_1->net',
            'logger_1->file'
          ]
        },
        logger_2:...
      }

    Return a dict mapping the status of those configs:
      {
        logger_1: {
          'configs': {
            'logger_1->off':  status,
            'logger_1->net':  status,
            'logger_1->file': status'
          }
        },
        logger_2:...
      }

    """
    with self.config_lock:
      status_list = self.read_stderr_rpc.supervisor.getAllProcessInfo()
      status_map = {s.get('name', None):s for s in status_list}

      status_result = {}
      for config in self.running_configs():
        cleaned_config_name = self._clean_name(config)
        config_status = status_map[cleaned_config_name].get('statename')
        status_result[config] = config_status

    return status_result

  ############################
  def read_stderr(self, configs=None, group=None, maxchars=1000):
    """Read the stderr from the named configs and return result in a dict of

       {config_1: config_1_stderr,
        config_2: config_2_stderr,
        ...
       }

    configs - a list of config names whose stderr should be read. If omitted,
        will read stderr of all active configs.

    group - process group in which the configs were defined; will be
        prepended to config names.

    maxchars - maximum number of characters to read from each log
    """
    if configs is None:
      configs = self.running_configs()

    results = {}
    with self.config_lock:
      for config in configs:
        # If we've got a group, need to prefix config name with it
        normalized_config = self._clean_name(config)
        if group:
          normalized_config = group + ':' + normalized_config

        # Initialize last read position of any configs we've not yet read
        if not config in self.read_stderr_offset:
          self.read_stderr_offset[config] = 0
        offset = self.read_stderr_offset[config]

        # Read stderr from config, iterating until we've got
        # everything from it.
        try:
          results[config] = ''
          overflow = True
          while overflow:
            # Get a chunk of stderr, update offset, and see if there's more
            getTail = self.read_stderr_rpc.supervisor.tailProcessStderrLog
            result, offset, overflow = getTail(normalized_config,
                                               offset, maxchars)
            results[config] += result
            self.read_stderr_offset[config] = offset

        # If we've barfed on the read, give up on this config for now
        except XmlExpatError as e:
          logging.debug('XML parse error while reading stderr: %s', str(e))
        except (ResponseNotReady, CannotSendRequest) as e:
          logging.warning('Http error: %s', str(e))
          #self.read_stderr_rpc = self._create_supervisor_connection()

    return results

  ############################
  def create_new_supervisor_file(self, configs, group=None,
                                 supervisor_logfile_dir=None,
                                 user=None, base_dir=None):
    """Create a new configuration file for supervisord to read.

    configs - a dict of {logger_name:{config_name:config_spec}} entries.

    group - process group in which the configs will be defined; will be
        prepended to config names.

    supervisor_logfile_dir - path to which logger stderr/stdout should be
        written.

    user - user name under which processes should run. Will default to
        current user.

    base_dir - directory from which executables should be called.
    """
    logging.warning('Writing new configurations to "%s"',
                    self.supervisor_logger_config_file)

    # Fill in some defaults if they weren't provided
    user = user or getpass.getuser()
    base_dir = base_dir or dirname(dirname(realpath(__file__)))

    # We'll build the string for the supervisord config file in 'config_str'
    content_str = '\n'.join([
      '; DO NOT EDIT UNLESS YOU KNOW WHAT YOU\'RE DOING. This configuration ',
      '; file was produced automatically by the logger_supervisor.py script',
      '; and will be overwritten by it as well.',
      ''
      ])

    config_names = []
    for logger, logger_configs in configs.items():
      for config_name, config in logger_configs.items():
        # Supervisord doesn't like '/' in program names
        config_name = self._clean_name(config_name)
        config_names.append(config_name)

        # If a logger isn't "runnable" because it doesn't have readers
        # or writers (e.g. if it's an "off" config), then it'll
        # terminate quietly after starting. Don't want to complain
        # (startsecs=0) or restart (autorestart=false) it.
        runnable = 'readers' in config and 'writers' in config

        replacement_fields = {
          'config_name': config_name,
          'config_json': json.dumps(config),
          'directory': base_dir,
          'autorestart': 'true' if runnable else 'false',
          'startsecs': '5' if runnable else '0',
          'startretries': self.max_tries,
          'user': user,
          'comment_log': '' if self.supervisor_logfile_dir else ';',
          'logfile_dir': self.supervisor_logfile_dir,
          'logger': logger,
          'log_v': ''  # set to '-v' or '-v -v' to increase log level
          }
        content_str += SUPERVISOR_LOGGER_TEMPLATE.format(**replacement_fields)

    # If we've been given a group name, group all the logger configs
    # together under it so we can start them all at the same time with
    # a single call.
    if group:
      content_str += '\n'.join([
        '[group:%s]' % group,
        'programs=%s' % ','.join(config_names),
        ''
      ])

    # Open and write the config file.
    with open(self.supervisor_logger_config_file, 'w') as config_file:
      config_file.write(content_str)

    # Get supervisord to reload the new file and refresh groups.
    self.supervisor_rpc.supervisor.reloadConfig()
    if group:
      try:
        self.supervisor_rpc.supervisor.removeProcessGroup(group)
      except XmlRpcFault:
        pass
      try:
        self.supervisor_rpc.supervisor.addProcessGroup(group)
      except XmlRpcFault:
        pass

  ############################
  def shutdown(self):
    """If we started the supervisord process, then tell it to shut down.
    """
    if self.supervisord_proc:
      try:
        self.supervisor_rpc.supervisor.shutdown()
      except (XmlRpcFault, ConnectionRefusedError):
        logging.debug('Caught shutdown fault')

################################################################################
################################################################################
class LoggerSupervisor:
  ############################
  def __init__(self,
               api, supervisor, data_server_websocket=None,
               supervisor_logfile_dir=None,
               interval=0.5, logger_log_level=logging.WARNING):
    """Read desired/current logger configs from Django DB and try to run the
    loggers specified in those configs.
    ```
    api - ServerAPI (or subclass) instance by which LoggerManager will get
          its data store updates

    supervisor - a SupervisorConnector object to use to manage
          logger processes.

    data_server_websocket - websocket address to which we are going to send
          our status updates.

    supervisor_logfile_dir - Directory where logger stderr/stdout will
          be written.

    interval - number of seconds to sleep between checking/updating loggers

    logger_log_level - At what logging level our component loggers
          should operate.
    ```
    """
    # Set signal to catch SIGTERM and convert it into a
    # KeyboardInterrupt so we can shut things down gracefully.
    try:
      signal.signal(signal.SIGTERM, kill_handler)
    except ValueError:
      logging.warning('LoggerSupervisor not running in main thread; '
                      'shutting down with Ctl-C may not work.')

    # api class must be subclass of ServerAPI
    if not issubclass(type(api), ServerAPI):
      raise ValueError('Passed api "%s" must be subclass of ServerAPI' % api)
    self.api = api
    self.interval = interval
    self.logger_log_level = logger_log_level
    self.quit_flag = False

    # The XMLRPC connector to supervisord
    self.supervisor = supervisor

    # Where we store the latest status/error reports.
    self.status = {}
    self.errors = {}

    # We'll loop to check the API for updates to our desired
    # configs. Do this in a separate thread. Also keep track of
    # currently active configs so that we know when an update is
    # actually needed.
    self.update_configs_thread = None
    self.config_lock = threading.Lock()

    self.active_configs = set()       # which of those configs are active now?

    # Data server to which we're going to send status updates
    if data_server_websocket:
      self.data_server_writer = CachedDataWriter(data_server_websocket)
    else:
      self.data_server_writer = None

    # Fetch the complete set of loggers and configs from API; store
    # them in self.loggers and create a .ini file for supervisord to
    # run them.
    self._build_new_config_file()

    # Stash a map of loggers->configs and configs->loggers
    self.loggers = self.api.get_loggers()
    self.config_to_logger = {}
    for logger in self.loggers:
      for config in self.loggers[logger].get('configs', []):
        self.config_to_logger[config] = logger

  ############################
  def start(self):
    """Start the threads that make up the LoggerSupervisor operation:

    1. Configuration update loop
    2. Loop to read logger stderr/status and either output it or
       transmit it to a cached data server

    Start threads as daemons so that they'll automatically terminate
    if the main thread does.
    """
    # Update configs in a separate thread.
    self.update_configs_thread = threading.Thread(
      name='update_configs_loop',
      target=self._update_configs_loop, daemon=True)
    self.update_configs_thread.start()

    # Start a separate thread to read logger status and stderr. If we've
    # got the address of a data server websocket, send our updates to it.
    self.read_logger_status_thread = threading.Thread(
      name='read_logger_status_loop',
      target=self._read_logger_status_loop, daemon=True)
    self.read_logger_status_thread.start()

  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True
    self.supervisor.shutdown()

  ############################
  def _build_new_config_file(self):
    """Fetch latest dict of configs from API. Update self.loggers to
    reflect them and build a .ini file to run them.
    """
    # Stash an updated map of loggers->configs and configs->loggers.
    # While we're doing that, also (inefficiently) grab definition
    # string for each config one at a time from the API.
    self.loggers = self.api.get_loggers()
    self.config_to_logger = {}
    logger_config_strings = {}
    for logger, configs in self.loggers.items():
      config_names = configs.get('configs', [])
      # Map config_name->logger
      for config in self.loggers[logger].get('configs', []):
        self.config_to_logger[config] = logger

      # Map logger->{config_name:config_definition_str,...}
      logger_config_strings[logger] = {
          config_name:api.get_logger_config(config_name)
          for config_name in config_names}

    # Now create a .ini file of those configs for supervisord to run.
    with self.config_lock:
      self.supervisor.create_new_supervisor_file(
        configs=logger_config_strings,
        supervisor_logfile_dir=args.supervisor_logfile_dir,
        group='logger')

    # Finally, reset the currently active configurations
    self._update_configs()

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
    """Get list of new (latest) configs. If any have changed,

    1. Shut down any configs that aren't a part of new active configs.
    2. Start and newly-active configs.
    """
    with self.config_lock:
      try:
        # Get new configs in dict {logger:{'configs':[config_name,...]}}
        new_logger_configs = self.api.get_logger_configs()
        new_configs = set([new_logger_configs[logger].get('name', None)
                           for logger in new_logger_configs])
      except (AttributeError, ValueError):
        return

      # If configs have changed, start new ones and stop old ones.
      if new_configs == self.active_configs:
        return

      configs_to_start = new_configs - self.active_configs
      configs_to_stop = self.active_configs - new_configs

      if configs_to_stop:
        logging.warning('Stopping configs: %s', configs_to_stop)
        self.supervisor.stop_configs(configs_to_stop, group='logger')

        # Alert the data server which configs we're stopping
        for config in configs_to_stop:
          logger = self.config_to_logger[config]
          self._write_log_message_to_data_server('stderr:logger:' + logger,
                                                 'Stopping config ' + config)

        # Grab any last output from the configs we've stopped
        self._read_and_send_logger_stderr(configs_to_stop)

      if configs_to_start:
        logging.warning('Starting new configs: %s', configs_to_start)
        self.supervisor.start_configs(configs_to_start, group='logger')

        # Alert the data server which configs we're starting
        for config in configs_to_start:
          logger = self.config_to_logger[config]
          self._write_log_message_to_data_server('stderr:logger:' + logger,
                                                 'Starting config ' + config)
      # Cache our new configs for the next time around
      self.active_configs = new_configs

  ############################
  def _read_and_send_cruise_definition(self):
    """Assemble and send a cruise definition to the cached data server.
    """
    # Assemble information from DB about what loggers should
    # exist and what states they *should* be in. We'll send
    # this to the cached data server whenever it changes (or
    # if it's been a while since we have).
    #
    # Looks like:
    # {'active_mode': 'log',
    #  'cruise_id': 'NBP1406',
    #  'loggers': {'PCOD': {'active': 'PCOD->file/net',
    #                       'configs': ['PCOD->off',
    #                                   'PCOD->net',
    #                                   'PCOD->file/net',
    #                                   'PCOD->file/net/db']},
    #               next_logger: next_configs,
    #               ...
    #             },
    #  'modes': ['off', 'monitor', 'log', 'log+db']
    # }
    try:
      cruise = api.get_configuration() # a Cruise object
      cruise_def = {
        'cruise_id': cruise.id,
        'loggers': api.get_loggers(),
        'modes': cruise.modes(),
        'active_mode': cruise.current_mode.name
      }
      self._write_record_to_data_server('status:cruise_definition', cruise_def)
    except (AttributeError, ValueError):
      logging.debug('No cruise definition found')

  ############################
  def _write_log_message_to_data_server(self, field_name, message,
                                        log_level=logging.WARNING):
    """Send something that looks like a logging message to the cached data
    server.
    """
    asctime = datetime.datetime.utcnow().isoformat()
    asctime = asctime.replace('T',' ',1) + 'Z'
    record = {'asctime': asctime, 'message': message}

    logging.warning('sending log message %s: %s', field_name, record)
    self._write_record_to_data_server(field_name, json.dumps(record))

  ############################
  def _write_record_to_data_server(self, field_name, record):
    """Format and label a record and send it to the cached data server.
    """
    if self.data_server_writer:
      das_record = DASRecord(fields={field_name: record})
      logging.debug('DASRecord: %s' % das_record)
      self.data_server_writer.write(das_record)

  ############################
  def _read_and_send_logger_stderr(self, configs=None):
    """Grab logger stderr messages and send them off to cached data server
    via websocket.
    """
    if configs is None:
      configs = self.supervisor.running_configs()

    stderr_results = self.supervisor.read_stderr(configs, group='logger')
    for config, stderr_lines in stderr_results.items():
      logger = self.config_to_logger[config]
      field_name = 'stderr:logger:' + logger
      for line in stderr_lines.split('\n'):
        if not line:
          continue

        if self.data_server_writer:
          # Parse the logging line into a DASRecord
          try:
            components = line.split(' ', maxsplit=5)
            (r_date, r_time, r_levelno, r_levelname,  r_filename_lineno,
             r_message) = components
            r_filename, r_lineno = r_filename_lineno.split(':')
            record = {
              'asctime': r_date + ' ' + r_time,
              'levelno': r_levelno,
              'levelname': r_levelname,
              'filename': r_filename,
              'lineno': r_lineno,
              'message': r_message
              }
          except ValueError:
            logging.debug('Failed to parse: "%s"', line)
            record = {'message': line}

          # Send the record off the the data server
          self._write_record_to_data_server(field_name, json.dumps(record))

        else:
          # If no data server, just print to stdout
          print(logger + ': ' + line)

  ############################
  def _read_and_send_logger_status(self):
    """Grab logger status message from supervisor and send to cached data
    server via websocket.
    """
    status_result = self.supervisor.read_status()

    # Map status to logger
    status_map = {}
    for config, status in status_result.items():
      logger = self.config_to_logger[config]
      status_map[logger] = {'config':config, 'status':status}

    if self.data_server_writer:
      self._write_record_to_data_server('status:logger_status', status_map)
    else:
      logging.debug('Got logger status: %s', status_map)

  ############################
  def _read_logger_status_loop(self):
    """Iteratively grab messages to send to cached data server and send
    them off via websocket.
    """
    SEND_CRUISE_EVERY_N_SECONDS = 10
    SEND_STATUS_EVERY_N_SECONDS = 3

    last_cruise_definition = 0
    last_status = 0
    while not self.quit_flag:
      now = time.time()

      if now - last_cruise_definition > SEND_CRUISE_EVERY_N_SECONDS:
        self._read_and_send_cruise_definition()
        last_cruise_definition = now

      if now - last_status > SEND_STATUS_EVERY_N_SECONDS:
        self._read_and_send_logger_status()
        last_status = now

      self._read_and_send_logger_stderr()
      time.sleep(1)

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
  websocket_port = int(data_server_websocket.split(':')[-1])
  server = CachedDataServer(port=websocket_port, interval=data_server_interval)

  # The server will start serving in its own thread after
  # initialization, but we need to manually fire up the cleanup loop
  # if we want it. Maybe we should have this also run automatically in
  # its own thread after initialization?
  server.cleanup_loop()

################################################################################
if __name__ == '__main__':
  import argparse
  import atexit
  import readline

  from server.server_api_command_line import ServerAPICommandLine

  parser = argparse.ArgumentParser()
  parser.add_argument('--config', dest='config', action='store',
                      help='Name of configuration file to load.')
  parser.add_argument('--mode', dest='mode', action='store', default=None,
                      help='Optional name of mode to start system in.')

  parser.add_argument('--database', dest='database', action='store',
                      choices=['memory', 'django', 'hapi'],
                      default='memory', help='What backing store database '
                      'to use.')

  # Arguments for the SupervisorConnector
  supervisor_group = parser.add_mutually_exclusive_group()
  supervisor_group.add_argument('--start_supervisor',
                                dest='start_supervisor', action='store_true',
                                default=False, help='Start local copy of '
                                'supervisord, building its own config file '
                                'in a temporary file. Note that if we start '
                                'our own supervisor, it and the loggers will '
                                'exit when we do. If we use an external '
                                'instance, the loggers will continue to in '
                                'whatever state they were last in after we '
                                'exit')

  supervisor_group.add_argument('--supervisor_logger_config_file',
                                dest='supervisor_logger_config_file',
                                default=None,
                                action='store', help='Location of file where '
                                'supervisord should look for logger process '
                                'definitions. Mutually exclusive with '
                                '--start_supervisor.')

  parser.add_argument('--supervisor_port', dest='supervisor_port',
                      action='store', type=int, default=DEFAULT_SUPERVISOR_PORT,
                      help='Localhost port at which supervisor should serve.')

  parser.add_argument('--supervisor_logfile_dir',
                      dest='supervisor_logfile_dir', action='store',
                      default=DEFAULT_SUPERVISOR_LOGFILE_DIR,
                      help='Directory where supervisor and logger '
                      'stderr/stdout will be written.')

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
                      type=float, default=1,
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
  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

  log_level = LOG_LEVELS[min(args.verbosity, max(LOG_LEVELS))]
  logging.basicConfig(format=DEFAULT_LOGGING_FORMAT)

  # What level do we want our component loggers to write?
  logger_log_level = LOG_LEVELS[min(args.logger_verbosity, max(LOG_LEVELS))]

  ############################
  # First off, start any servers we're supposed to be running

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
  # Instantiate API - a Are we using an in-memory store or Django
  # database as our backing store? Do our imports conditionally, so
  # they don't actually have to have Django if they're not using it.
  if args.database == 'django':
    from django_gui.django_server_api import DjangoServerAPI
    api = DjangoServerAPI()
  elif args.database == 'memory':
    from server.in_memory_server_api import InMemoryServerAPI
    api = InMemoryServerAPI()
  elif args.database == 'hapi':
    from hapi.hapi_server_api import HapiServerAPI
    api = HapiServerAPI()
  else:
    raise ValueError('Illegal arg for --database: "%s"' % args.database)

  # Now that API is defined, tack on one more logging handler: one
  # that passes messages to API.
  # TODO: decide if we even need this. Disabled for now
  #logging.getLogger().addHandler(WriteToAPILoggingHandler(api))

  ############################
  # Create a connector to a supervisor, optionally starting up a local
  # one for our own use.
  supervisor = SupervisorConnector(
    start_supervisor=args.start_supervisor,
    supervisor_logger_config_file=args.supervisor_logger_config_file,
    supervisor_port=args.supervisor_port,
    supervisor_logfile_dir=args.supervisor_logfile_dir,
    max_tries=args.max_tries,
    log_level=log_level)

  ############################
  # Create our LoggerSupervisor
  logger_supervisor = LoggerSupervisor(
    api=api, supervisor=supervisor,
    data_server_websocket=args.data_server_websocket,
    supervisor_logfile_dir=args.supervisor_logfile_dir,
    interval=args.interval,
    logger_log_level=logger_log_level)

  # When an active config changes in the database, update our configs here
  api.on_update(callback=logger_supervisor._update_configs)

  # When new configs are loaded, update our file of config processes
  api.on_load(callback=logger_supervisor._build_new_config_file)

  # When told to quit, shut down gracefully
  api.on_quit(callback=logger_supervisor.quit)

  ############################
  # Start all the various LoggerManager threads running
  logger_supervisor.start()

  ############################
  # If they've given us an initial configuration, get and load it.
  if args.config:
    config = read_config(args.config)
    api.load_configuration(config)
    api.message_log(source=SOURCE_NAME, user='(%s@%s)' % (USER, HOSTNAME),
                    log_level=api.INFO,
                    message='started with: %s' % args.config)
  if args.mode:
    if not args.config:
      raise ValueError('Argument --mode can only be used with --config')
    api.set_active_mode(args.mode)
    api.message_log(source=SOURCE_NAME, user='(%s@%s)' % (USER, HOSTNAME),
                    log_level=api.INFO,
                    message='initial mode (%s@%s): %s' % (USER, HOSTNAME,
                                                          args.mode))
  try:
    # If no console, just wait for the configuration update thread to
    # end as a signal that we're done.
    if args.no_console:
      logging.warning('--no-console specified; waiting for LoggerManager '
                   'to exit.')
      if logger_supervisor.update_configs_thread:
        logger_supervisor.update_configs_thread.join()
      else:
        logging.warning('LoggerManager has no update_configs_thread? '
                        'Exiting...')

    else:
      # Create reader to read/process commands from stdin. Note: this
      # needs to be in main thread for Ctl-C termination to be properly
     # caught and processed, otherwise interrupts go to the wrong places.

      # Set up command line interface to get commands. Start by
      # reading history file, if one exists, to get past commands.
      hist_filename = '.openrvdas_logger_supervisor_history'
      hist_path = os.path.join(os.path.expanduser('~'), hist_filename)
      try:
        readline.read_history_file(hist_path)
        # default history len is -1 (infinite), which may grow unruly
        readline.set_history_length(1000)
      except (FileNotFoundError, PermissionError):
        pass
      atexit.register(readline.write_history_file, hist_path)

      command_line_reader = ServerAPICommandLine(api=api)
      command_line_reader.run()

  except KeyboardInterrupt:
    pass
  logging.debug('Done with logger_supervisor.py - exiting')
