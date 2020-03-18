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
import psutil
import signal
import socket  # to get hostname
import subprocess
import sys
import tempfile
import threading
import time
import websockets

from parse import parse

# For communicating with supervisord server
from xmlrpc.client import ServerProxy
from xmlrpc.client import Fault as XmlRpcFault
from xml.parsers.expat import ExpatError as XmlExpatError
from http.client import CannotSendRequest as CannotSendRequest
from http.client import ResponseNotReady as ResponseNotReady

from os.path import dirname, realpath

# Add the openrvdas components onto sys.path
sys.path.append(dirname(dirname(realpath(__file__))))

from server.server_api import ServerAPI

# Imports for running CachedDataServer
from server.cached_data_server import CachedDataServer

# For sending stderr to CachedDataServer
from logger.utils.read_config import read_config
from logger.writers.cached_data_writer import CachedDataWriter
from logger.writers.text_file_writer import TextFileWriter
from logger.utils.stderr_logging import StdErrLoggingHandler

from logger.utils.das_record import DASRecord
from logger.utils.stderr_logging import DEFAULT_LOGGING_FORMAT
from logger.transforms.to_das_record_transform import ToDASRecordTransform
from logger.writers.composed_writer import ComposedWriter

# Name of the supervisord executable
SUPERVISORD = 'supervisord'

# When we kill any leftover supervisord process, we want to make sure
# to only kill the one(s) associated with the logger manager. To do
# that, we flag our instance with a name under which we can look the
# process up.
SUPERVISORD_NAME = 'logger_manager_supervisor'

DEFAULT_GROUP = 'logger'
DEFAULT_MAX_TRIES = 3

SOURCE_NAME = 'LoggerManager'
USER = getpass.getuser()
HOSTNAME = socket.gethostname()

DEFAULT_DATA_SERVER_WEBSOCKET = 'localhost:8766'

DEFAULT_SUPERVISOR_DIR = '/var/tmp/openrvdas/supervisor'
DEFAULT_SUPERVISOR_PORT = 9002
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
chmod=0770                  ; socket file mode (default 0700)
;chown={user}:{group}       ; socket file uid:gid owner
{username_auth}             ; default is no username (open server)
{password_auth}             ; default is no password (open server)

[inet_http_server]         ; inet (TCP) server disabled by default
;port=localhost:{port}      ; ip_address:port specifier, *:port for all iface
port={host}:{port}         ; ip_address:port specifier, *:port for all iface
{username_auth}            ; default is no username (open server)
{password_auth}            ; default is no password (open server)

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
;user={user}        ; setuid to this UNIX account at startup; recommended if root

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
{username_auth}            ; should be same as in [*_http_server] if set
{password_auth}            ; should be same as in [*_http_server] if set

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
;user={user}
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
               start_supervisor_in=None,
               supervisor_logger_config=None,
               supervisor_host='localhost',
               supervisor_port=DEFAULT_SUPERVISOR_PORT,
               supervisor_logfile_dir=DEFAULT_SUPERVISOR_LOGFILE_DIR,
               supervisor_auth=None,
               group=DEFAULT_GROUP,
               max_tries=DEFAULT_MAX_TRIES,
               log_level=logging.WARNING):
    """Connect to a supervisord process, or start our own to manage
    processes.  If starting our own, do so in a tempdir of our own
    creation that will go away when connector is destroyed.
    ```
    start_supervisor_in - Start local copy of supervisord and set up
          socket, pid and conf.d in this directory. Mutually exclusive
          with supervisor_logger_config being specified. If neither are
          specified, will default to DEFAULT_SUPERVISOR_DIR.

    supervisor_logger_config - Location of file where supervisord should look
          for logger process definitions. Mutually exclusive with
          --start_supervisor_in flag.

    supervisor_host - Hostname at which supervisor should serve ('*' means any).

    supervisor_port - Host port at which supervisor should serve.

    supervisor_logfile_dir - Directory where supevisord and logger
          stderr/stdout will be written.

    supervisor_auth - If provided, a username:password string to be used
          to authenticate to the supervisor instance. If omitted, no auth
          will be assumed.

    group - process group in which the configs will be defined; will be
          prepended to config names.

    max_tries = Number of times a failed logger should be retried if it
          fails on startup.
    ```
    """
    # If no guidance on starting supervisor, start our own copy in
    # default location.
    if not start_supervisor_in and not supervisor_logger_config:
      start_supervisor_in = DEFAULT_SUPERVISOR_DIR

    self.supervisor_dir = start_supervisor_in
    self.supervisor_logger_config = supervisor_logger_config
    self.supervisor_host = supervisor_host
    self.supervisor_port = supervisor_port
    self.supervisor_logfile_dir = supervisor_logfile_dir
    self.supervisor_auth = supervisor_auth
    self.group = group
    self.max_tries = max_tries
    self.log_level = log_level

    # Define these right at start, because if we shut down prematurely
    # during initialization, the destructor is going to look for them.
    self.supervisor_rpc = None
    self.supervisor_rpc_lock = threading.Lock()
    self.supervisord_proc = None

    if bool(start_supervisor_in) == bool(supervisor_logger_config):
      logging.fatal('SupervisorConnector must have either '
                    '"start_supervisor_in" or "supervisor_logger_config" '
                    'as non-empty, but not both.')
      sys.exit(1)

    # If we're starting our own local copy of supervisor, create the
    # relevant config files in a temp directory.
    if start_supervisor_in:
      self.supervisord_proc = self._start_supervisor()

    # Now that the preliminaries are done, try to connect to server.
    with self.supervisor_rpc_lock:
      self.supervisor_rpc = self._create_supervisor_connection()

    # Create a second connection that we will use to read logger
    # process stderr. We'll guard reads from this from stepping on
    # each other by means of a thread lock.
    self.read_stderr_rpc_lock = threading.Lock()
    with self.read_stderr_rpc_lock:
      self.read_stderr_rpc =  self._create_supervisor_connection()

    # A lock for information we maintain about current configurations
    self.config_lock = threading.Lock()
    self.read_stderr_offset = {}  # how much of each stderr we've read

    # Finally, keep track of the configs that are currently active
    self._running_configs = set()

  ############################
  def _start_supervisor(self):
    logging.info('Starting standalone supervisord instance in %s',
                 self.supervisor_dir)
    # Make the working directory that supervisord will run in if it
    # doesn't exist and, while we're at it, make the supervisor.d/
    # subdirectory of that where we'll put our logger config .ini file.
    subdir = self.supervisor_dir + '/supervisor.d'
    if not os.path.exists(subdir):
      os.makedirs(subdir)

    # Create the supervisor config file
    supervisor_config_filename = self.supervisor_dir + '/supervisord.ini'
    logging.info('Creating supervisord file in %s', supervisor_config_filename)
    supervisor_log_level = {logging.WARNING: 'warn',
                            logging.INFO: 'info',
                            logging.DEBUG: 'debug'}.get(self.log_level, 'warn')
    if self.supervisor_auth:
      auth_user, auth_password = self.supervisor_auth.split(':')
      username_auth = 'username=%s' % auth_user
      password_auth = 'password=%s' % auth_password
    else:
      username_auth = ';'
      password_auth = ';'

    config_args = {
      'supervisor_dir': self.supervisor_dir,
      'logfile_dir': self.supervisor_logfile_dir,
      'host': self.supervisor_host,
      'port': self.supervisor_port,
      'user': getpass.getuser(),
      'group': getpass.getuser(),
      'username_auth': username_auth,
      'password_auth': password_auth,
      'log_level': supervisor_log_level,
    }
    supervisor_config_str = SUPERVISORD_TEMPLATE.format(**config_args)
    with open(supervisor_config_filename, 'w') as supervisor_config_file:
      supervisor_config_file.write(supervisor_config_str)

    # Create an empty logger.ini file to prevent supervisor from
    # complaining that there are no matching .ini files when it
    # starts up. Petty, I know, but the warning could cause folks to
    # worry about the wrong thing if something else is amiss.
    self.supervisor_logger_config = \
          self.supervisor_dir + '/supervisor.d/loggers.ini'
    open(self.supervisor_logger_config, 'a').close()

    # Make sure supervisord exists and is on path
    try:
      subprocess.check_output(['which', SUPERVISORD])
    except subprocess.CalledProcessError:
      logging.fatal('Supervisor executable "%s" not found', SUPERVISORD)
      sys.exit(1)

    # Make sure tlhere are no other copies of us running.
    self._kill_supervisor()

    # And start the local supervisord
    supervisord_cmd = ['/usr/bin/env', SUPERVISORD,
                       '-i', SUPERVISORD_NAME,
                       '-n', '-c', supervisor_config_filename]

    self.supervisord_proc = subprocess.Popen(args=supervisord_cmd,
                                             stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL)
    time.sleep(0.1)
    if self.supervisord_proc.poll() is not None:
      logging.fatal('Unable to start process %s; quitting.',
                    ' '.join(supervisord_cmd))
      sys.exit(1)
    return self.supervisord_proc

  ############################
  def _create_supervisor_connection(self):
    """Connect to server. If we fail, sleep a little and try again."""
    while True:
      auth = self.supervisor_auth + '@' if self.supervisor_auth else ''
      host = self.supervisor_host
      if host == '*':
        host = 'localhost'
      port = self.supervisor_port
      supervisor_url = 'http://%s%s:%d/RPC2' % (auth, host, port)
      logging.info('Connecting to supervisor at %s', supervisor_url)

      supervisor_rpc = ServerProxy(supervisor_url)
      try:
        supervisor_state = supervisor_rpc.supervisor.getState()
        if supervisor_state['statename'] == 'RUNNING':
          break

        logging.error('Supervisord is not running. State is "%s"',
                      supervisor_state['statename'])
      except ConnectionRefusedError:
        logging.info('Unable to connect to supervisord at %s; trying again.',
                     supervisor_url)
      time.sleep(5)
      logging.info('Retrying connection to %s', supervisor_url)

    # Return with our connection
    return supervisor_rpc

  ############################
  def _kill_supervisor(self):
    # Shut down any processes
    with self.supervisor_rpc_lock:
      if self.supervisor_rpc:
        try:
          self.supervisor_rpc.supervisor.stopAllProcesses()
        except (ConnectionRefusedError, CannotSendRequest, XmlRpcFault) as e:
          pass

      # If we were running our own supervisor process, shut it down
      # (first ask it to shut down, then kill it dead, dead, dead).
      if self.supervisord_proc and self.supervisor_rpc:
        try:
          self.supervisor_rpc.supervisor.shutdown()
        except (ConnectionRefusedError, CannotSendRequest, XmlRpcFault):
          pass
        self.supervisord_proc.kill()
        self.supervisord_proc.wait()

    # Make sure there are no other copies of us running.
    for process in psutil.process_iter():
      try:
        cmdline = process.cmdline()
        if (len(cmdline) == 7 and SUPERVISORD in cmdline[1] and
            cmdline[2] == '-i' and cmdline[3] == SUPERVISORD_NAME):
          process.kill()
          logging.info('Killed existing supervisor process %d', process.pid)
          break
      except (psutil.AccessDenied, psutil.ZombieProcess) as e:
        logging.debug('Got psutil error for %s: %s', process, e)

  ############################
  def shutdown(self):
    """Shut down our own supervisor instance if we've spawned one. Also
    check if there are any old, conflicting logger_manager-started
    supervisor processes running and kill them with prejudice.
    """
    if self.supervisord_proc:
      self._kill_supervisor()

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
  def start_configs(self, configs_to_start):
    """Ask supervisord to start the listed configs.

    configs_to_start - a list of config names that should be started.
    """
    configs = list(configs_to_start)  # so we can order results
    config_calls = []

    with self.config_lock:
      for config in configs:
        config = self._clean_name(config)  # get rid of objectionable characters
        if self.group:
          config = self.group + ':' + config
        config_calls.append({'methodName':'supervisor.startProcess',
                             'params':[config, False]})

    # Make calls in parallel and update set of currently-running
    # configs. If we fail, simply return and count on trying again
    # when the next update is called.
    try:
      with self.supervisor_rpc_lock:
        results = self.supervisor_rpc.system.multicall(config_calls)
    except (ConnectionRefusedError, ResponseNotReady, CannotSendRequest):
      return

    with self.config_lock:
      self._running_configs |= configs_to_start

    # Let's see what the results are
    bad_loggers = False
    for i in range(len(results)):
      result = results[i]
      config = configs[i]
      if type(result) is dict:
        if result['faultCode'] == 60:
          # We may get this when a new config is loaded and
          # _update_config is called manually, which may step on the
          # already-running _update_config_loop. It's not a problem.
          logging.info('Starting process %s, but already started', config)
        else:
          logging.info('Starting process %s: %s', config, result['faultString'])

  ############################
  def stop_configs(self, configs_to_stop):
    """Ask supervisord to stop the listed configs. Note that all logger
    configs are part of group 'logger', so we need to prefix all names
    with 'logger:' when talking to supervisord about them.

    configs_to_stop - a list of config names that should be stopped.
    """
    configs = list(configs_to_stop)  # so we can order results
    config_calls = []

    with self.config_lock:
      for config in configs:
        config = self._clean_name(config)  # get rid of objectionable characters
        if self.group:
          config = self.group + ':' + config
        config_calls.append({'methodName':'supervisor.stopProcess',
                             'params':[config, False]})

    # Make calls in parallel and update set of currently-running
    # configs. If we fail, simply return and count on trying again
    # when the next update is called.
    try:
      with self.supervisor_rpc_lock:
        results = self.supervisor_rpc.system.multicall(config_calls)
    except (ConnectionRefusedError, ResponseNotReady, CannotSendRequest):
      return

    with self.config_lock:
      self._running_configs = self._running_configs - configs_to_stop

    # Let's see what the results are
    for i in range(len(results)):
      result = results[i]
      config = configs[i]
      if type(result) is dict:
        if result['faultCode'] == 60:
          logging.debug('Stopping process %s, but already stopped', config)
        else:
          logging.debug('Stopping process %s: %s', config, result['faultString'])

  ############################
  def running_configs(self):
    """Return set of currently-running configs."""
    return self._running_configs

  ############################
  def check_status(self):
    """Read the RUNNING/STOPPED/FATAL/EXITED status of (nominally)
    currently-active configs:

      {
       'logger_1->file: 'RUNNING',
       'logger_2->file: 'RUNNING',
       'logger_3->file: 'FATAL',
       'logger_4->file: 'RUNNING',
       ...,
      }
    """
    with self.read_stderr_rpc_lock:
      try:
        status_list = self.read_stderr_rpc.supervisor.getAllProcessInfo()
      except (ConnectionRefusedError, XmlExpatError, XmlRpcFault) as e:
        logging.error('Error reading supervisor process status: %s', e)
        return {}

    status_map = {s.get('name', None):s for s in status_list}
    status_result = {}

    with self.config_lock:
      for config in self.running_configs():
        cleaned_config_name = self._clean_name(config)
        state = status_map.get(cleaned_config_name,{})
        status_result[config] = state.get('statename', None)

    return status_result

  ############################
  def read_stderr(self, configs=None, maxchars=1000):
    """Read the stderr from the named configs and return result in a dict of

       {config_1: config_1_stderr,
        config_2: config_2_stderr,
        ...
       }

    configs - a list of config names whose stderr should be read. If omitted,
        will read stderr of all active configs.

    maxchars - maximum number of characters to read from each log
    """
    if configs is None:
      configs = self.running_configs()

    results = {}
    read_fault = False
    with self.config_lock:
      for config in configs:
        # If we've got a group, need to prefix config name with it
        cleaned_config = self._clean_name(config)
        if self.group:
          cleaned_config = self.group + ':' + cleaned_config

        # Initialize last read position of any configs we've not yet read
        if not config in self.read_stderr_offset:
          self.read_stderr_offset[config] = 0
        offset = self.read_stderr_offset[config]

        # Read stderr from config, iterating until we've got
        # everything from it.
        results[config] = ''
        overflow = True

        # Create alias for function call to prettify the loop below
        getTail = self.read_stderr_rpc.supervisor.tailProcessStderrLog

        while overflow:
          # Get a chunk of stderr, update offset, and see if there's more
          try:
            with self.read_stderr_rpc_lock:
              result, offset, overflow = getTail(cleaned_config,
                                                 offset, maxchars)
            results[config] += result
            self.read_stderr_offset[config] = offset
          # If we've barfed on the read, give up on this config for now
          except XmlExpatError as e:
            logging.debug('XML parse error while reading stderr: %s', str(e))
            overflow = False
          except (ResponseNotReady, CannotSendRequest,
                  ConnectionRefusedError) as e:
            logging.info('HTTP error: %s', str(e))
            overflow = False

          # We can get these faults if our config has been updated on
          # disc but not reloaded.
          except XmlRpcFault as e:
            logging.info('XmlRpcFault %d: %s', e.faultCode, e.faultString)
            overflow = False
            read_fault = True

    if read_fault:
      pass
      #self.reload_config_file()
    return results

  ############################
  def create_new_supervisor_file(self, configs, supervisor_logfile_dir=None,
                                 user=None, base_dir=None):
    """Create a new configuration file for supervisord to read.

    configs - a dict of {logger_name:{config_name:config_spec}} entries.

    supervisor_logfile_dir - path to which logger stderr/stdout should be
        written.

    user - user name under which processes should run. Will default to
        current user.

    base_dir - directory from which executables should be called.
    """
    logging.info('Writing new configurations to "%s"',
                 self.supervisor_logger_config)

    # Fill in some defaults if they weren't provided
    user = user or getpass.getuser()
    base_dir = base_dir or dirname(dirname(realpath(__file__)))

    # We'll build the string for the supervisord config file in 'config_str'
    content_str = '\n'.join([
      '; DO NOT EDIT UNLESS YOU KNOW WHAT YOU\'RE DOING. This configuration ',
      '; file was produced automatically by the logger_manager.py script',
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

        # NOTE: supervisord has trouble with '%' in a string, so we
        # escape it by converting it to '%%'
        replacement_fields = {
          'config_name': config_name,
          'config_json': json.dumps(config).replace('%', '%%'),
          'directory': base_dir,
          'autorestart': 'true' if runnable else 'false',
          'startsecs': '2' if runnable else '0',
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
    if self.group and config_names:
      content_str += '\n'.join([
        '[group:%s]' % self.group,
        'programs=%s' % ','.join(config_names),
        ''
      ])

    # Open and write the config file.
    with open(self.supervisor_logger_config, 'w') as config_file:
      config_file.write(content_str)

    # Re-open the connections to make a clean slate of things
    with self.supervisor_rpc_lock:
      self.supervisor_rpc = self._create_supervisor_connection()
    with self.read_stderr_rpc_lock:
      self.read_stderr_rpc =  self._create_supervisor_connection()

    # And reload the config file
    self.reload_config_file()

  ############################
  def reload_config_file(self):
    """Tell our supervisor instance to reload config file and any groups."""
    logging.info('Reloading config file')

    # Included code from supervisorctl:
    # https://github.com/Supervisor/supervisorctl.py#L1158-L1224
    with self.supervisor_rpc_lock:
      supervisor = self.supervisor_rpc.supervisor
      try:
        result = supervisor.reloadConfig()
      except XmlRpcFault as e:
        logging.info('XmlRpc fault: %s', str(e))
        return
        #self.ctl.exitstatus = LSBInitExitStatuses.GENERIC
        #if e.faultCode == 6 # XmlRpcFaults.SHUTDOWN_STATE:
        #  logging.info('ERROR: already shutting down')
        #  return
        #else:
        #  raise

      added, changed, removed = result[0]
      #valid_gnames = set([self.group])
      valid_gnames = set()

      # NOTE: with valid_gnames defined as empty, as above, is the
      # below block even necessary?

      # If any gnames are specified we need to verify that they are
      # valid in order to print a useful error message.
      if valid_gnames:
        groups = set()
        for info in supervisor.getAllProcessInfo():
          groups.add(info['group'])
        # New gnames would not currently exist in this set so
        # add those as well.
        groups.update(added)

        for gname in valid_gnames:
          if gname not in groups:
            logging.info('ERROR: no such group: %s' % gname)

    for gname in removed:
      if valid_gnames and gname not in valid_gnames:
        continue
      results = supervisor.stopProcessGroup(gname)
      logging.info('stopped %s', gname)

      fails = [res for res in results
               if res['status'] == xmlrpc.Faults.FAILED]
      if fails:
        logging.warning('%s has problems; not removing', gname)
        continue
      supervisor.removeProcessGroup(gname)
      logging.info('removed process group %s', gname)

    for gname in changed:
      if valid_gnames and gname not in valid_gnames:
        continue
      supervisor.stopProcessGroup(gname)
      logging.info('stopped %s', gname)

      supervisor.removeProcessGroup(gname)
      supervisor.addProcessGroup(gname)
      logging.info('updated process group %s', gname)

    for gname in added:
      if valid_gnames and gname not in valid_gnames:
        continue
      supervisor.addProcessGroup(gname)
      logging.info('added process group %s', gname)

################################################################################
################################################################################
class LoggerManager:
  ############################
  def __init__(self,
               api, supervisor, data_server_websocket=None,
               supervisor_logfile_dir=None,
               interval=0.25, logger_log_level=logging.WARNING):
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
      logging.warning('LoggerManager not running in main thread; '
                      'shutting down with Ctl-C may not work.')

    # api class must be subclass of ServerAPI
    if not issubclass(type(api), ServerAPI):
      raise ValueError('Passed api "%s" must be subclass of ServerAPI' % api)
    self.api = api
    self.supervisor_logfile_dir = supervisor_logfile_dir
    self.interval = interval
    self.logger_log_level = logger_log_level
    self.quit_flag = False

    # The XMLRPC connector to supervisord
    self.supervisor = supervisor

    # Where we store the latest cruise definition and status reports.
    self.definition = {}
    self.definition_time = 0
    self.config_status = {}
    self.status_time = 0

    # We'll loop to check the API for updates to our desired
    # configs. Do this in a separate thread. Also keep track of
    # currently active configs so that we know when an update is
    # actually needed.
    self.update_configs_thread = None
    self.config_lock = threading.Lock()

    self.active_configs = set()  # which configs are active now?

    # Data server to which we're going to send status updates
    if data_server_websocket:
      self.data_server_writer = CachedDataWriter(data_server_websocket)
    else:
      self.data_server_writer = None

    # Stash a map of loggers->configs and configs->loggers
    try:
      self.loggers = self.api.get_loggers()
      self.config_to_logger = {}
      for logger in self.loggers:
        for config in self.loggers[logger].get('configs', []):
          self.config_to_logger[config] = logger
    except ValueError:
      logging.info('No cruise defined yet.')
      self.loggers = {}
      self.config_to_logger = {}

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

    # Update configs in a separate thread.
    self.update_configs_thread = threading.Thread(
      name='update_configs_loop',
      target=self._update_configs_loop, daemon=True)
    self.update_configs_thread.start()

    # Start a separate threads to read logger status and stderr. If we've
    # got the address of a data server websocket, send our updates to it.
    self.send_cruise_definition_loop_thread = threading.Thread(
      name='send_cruise_definition_loop',
      target=self._send_cruise_definition_loop, daemon=True)
    self.send_cruise_definition_loop_thread.start()

    self.send_logger_status_loop_thread = threading.Thread(
      name='send_logger_status_loop',
      target=self._send_logger_status_loop, daemon=True)
    self.send_logger_status_loop_thread.start()

    self.send_logger_stderr_loop_thread = threading.Thread(
      name='send_logger_stderr_loop',
      target=self._send_logger_stderr_loop, daemon=True)
    self.send_logger_stderr_loop_thread.start()

  ############################
  def quit(self):
    """Exit the loop and shut down all loggers."""
    self.quit_flag = True

  ############################
  def _build_new_config_file(self):
    """Fetch latest dict of configs from API. Update self.loggers to
    reflect them and build a .ini file to run them.
    """
    # Stash an updated map of loggers->configs and configs->loggers.
    # While we're doing that, also (inefficiently) grab definition
    # string for each config one at a time from the API.
    logging.info('New cruise definition detected - rebuilding supervisord '
                 'config file')
    try:
      self.loggers = self.api.get_loggers()
      with self.config_lock:
        self.config_to_logger = {}
        logger_config_strings = {}
        for logger, configs in self.loggers.items():
          config_names = configs.get('configs', [])
          # Map config_name->logger
          for config in self.loggers[logger].get('configs', []):
            self.config_to_logger[config] = logger

          # Map logger->{config_name:config_definition_str,...}
          logger_config_strings[logger] = {
            config_name: self.api.get_logger_config(config_name)
            for config_name in config_names}

    # If no cruise loaded, create an empty config file
    except ValueError:
      logging.info('No cruise defined yet - creating empty supervisor file')
      logger_config_strings = {}

    # Now create a .ini file of those configs for supervisord to run.
    with self.config_lock:
      self.supervisor.create_new_supervisor_file(
        configs=logger_config_strings,
        supervisor_logfile_dir=self.supervisor_logfile_dir)

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

    # First, see if we have any status report on the configs
    # yet. Status updates run in a separate thread, but may not have
    # kicked in yet. If not, get status now.
    if not self.config_status:
      logging.info('No config status found yet. Fetching one...')
      config_status = self.supervisor.check_status()
      if not config_status:
        logging.debug('Retrieved empty config status.')
      with self.config_lock:
        self.config_status = config_status
        self.status_time = time.time()

    with self.config_lock:
      # First, see if the configs we *think* are running really
      # are. If status is not found, it means that config has just
      # been loaded, and hasn't gotten a proper status eval yet. Let
      # it pass on this iteration. Note also that in our case,
      # 'EXITED' counts as running. It means that the logger ran and
      # terminated normally, as we would expect for an 'off' logger
      # config.
      non_running_configs = set()
      for config in self.active_configs:
        status = self.config_status.get(config, None)
        if status and status == 'STOPPED':
          non_running_configs.add(config)

      if non_running_configs:
        logging.warning('Active configs found stopped: %s', non_running_configs)

      # Get new configs in dict {logger:{'configs':[config_name,...]}}
      try:
        new_logger_configs = self.api.get_logger_configs()
      except ValueError:
        logging.debug('No loggers found.')
        return

      new_configs = set([new_logger_configs[logger].get('name', None)
                         for logger in new_logger_configs])

      # The configs we need to start are the new ones, plus any
      # non-running configs that we think *should* be running.
      configs_to_start = new_configs - self.active_configs
      configs_to_start |= non_running_configs

      configs_to_stop = self.active_configs - new_configs

    # We've now assembled our list of configs to start and stop. Do it.
    if configs_to_stop:
      logging.info('Stopping configs: %s', configs_to_stop)
      self.supervisor.stop_configs(configs_to_stop)

      # Alert the data server which configs we're stopping. Note: if
      # we've loaded a new file, logger and config may have
      # disappeared, in which case we punt.
      for config in configs_to_stop:
        logger = self.config_to_logger.get(config, None)
        if logger:
          self._write_log_message_to_data_server('stderr:logger:' + logger,
                                                 'Stopping config ' + config)

      # Grab any last output from the configs we've stopped
      self._read_and_send_logger_stderr(configs_to_stop)

    if configs_to_start:
      logging.info('Activating new configs: %s', configs_to_start)
      self.supervisor.start_configs(configs_to_start)

      # Alert the data server which configs we're starting.  Note:
      # if we've loaded a new file, logger and config may have
      # disappeared, in which case we punt.
      for config in configs_to_start:
        logger = self.config_to_logger.get(config, None)
        if not logger:
          continue
        self._write_log_message_to_data_server('stderr:logger:' + logger,
                                               'Start config ' + config)

    # Cache our new configs for the next time around
    with self.config_lock:
      self.active_configs = new_configs

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
    last_config_timestamp = 0

    while not self.quit_flag:
      try:
        # An ugly hack here: the Django API gives us a Cruise object,
        # while the in-memory API gives us a dict. UGH!
        cruise = self.api.get_configuration() # a Cruise object
        if type(cruise) is dict:
          loaded_time = cruise.get('loaded_time')
        else:
          loaded_time = cruise.loaded_time
        config_timestamp = datetime.datetime.timestamp(loaded_time)
      except (AttributeError, ValueError, TypeError):
        config_timestamp = 0

      # Have we got a config with a newer timestamp? If so, update the
      # supervisor config file and send the update to the console.
      if config_timestamp > last_config_timestamp:
        last_config_timestamp = config_timestamp
        self._build_new_config_file()
        try:
          if type(cruise) is dict:
            cruise_def = {
              'cruise_id': cruise.get('cruise', {}).get('id', ''),
              'config_timestamp': config_timestamp,
              'loggers': self.api.get_loggers(),
              'modes': cruise.get('modes', {}),
              'active_mode': cruise.get('active_mode','')
            }
          else:
            cruise_def = {
              'cruise_id': cruise.id,
              'config_timestamp': config_timestamp,
              'loggers': self.api.get_loggers(),
              'modes': cruise.modes(),
              'active_mode': cruise.active_mode.name
            }
          self._write_record_to_data_server(
            'status:cruise_definition', cruise_def)
        except (AttributeError, ValueError) as e:
          logging.info('No cruise definition found: %s', e)

      # Whether or not we've sent an update, sleep
      time.sleep(self.interval * 2)

  ############################
  def _send_logger_status_loop(self):
    """Grab logger status message from supervisor and send to cached data
    server via websocket. Also send cruise mode as separate message.
    """
    while not self.quit_flag:
      now = time.time()
      try:
        config_status = self.supervisor.check_status()
        with self.config_lock:
          # Stash status, note time and send update
          self.config_status = config_status
          self.status_time = now

          # Map status to logger
          status_map = {}
          for config, status in config_status.items():
            logger = self.config_to_logger.get(config, None)
            if logger:
              status_map[logger] = {'config':config, 'status':status}
        self._write_record_to_data_server('status:logger_status', status_map)

        # Now get and send cruise mode
        mode_map = { 'active_mode': self.api.get_active_mode() }
        self._write_record_to_data_server('status:cruise_mode', mode_map)
      except ValueError as e:
        logging.warning('Error while trying to send logger status: %s', e)
      time.sleep(self.interval)

  ############################
  def _send_logger_stderr_loop(self):
    """Iteratively grab messages to send to cached data server and send
    them off via websocket.
    """
    while not self.quit_flag:
      self._read_and_send_logger_stderr()
      time.sleep(self.interval)

  ############################
  def _write_log_message_to_data_server(self, field_name, message,
                                        log_level=logging.INFO):
    """Send something that looks like a logging message to the cached data
    server.
    """
    asctime = datetime.datetime.utcnow().isoformat() + 'Z'
    record = {'asctime': asctime, 'levelno': log_level,
              'levelname': logging.getLevelName(log_level), 'message': message}
    self._write_record_to_data_server(field_name, json.dumps(record))

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

  ############################
  def _read_and_send_logger_stderr(self, configs=None):
    """Grab logger stderr messages and send them off to cached data server
    via websocket.
    """

    def parse_and_send_message(field_name, message):
      """Inner function that parses a (possibly multi-line) stderr message
      and sends it to the cached data server (or prints it out if we
      don't have a cached data server).
      """
      # If no data server, just print to stdout
      if not self.data_server_writer:
        logging.info(field_name + ': ' + message)
        return

      # Try parsing the expected format
      format = '{asctime:S} {levelno:d} {levelname:S} ' \
               '{filename:S}:{lineno:d} {message}'
      result = parse(format, message)

      # If that parse failed, try parsing with date and time as
      # separate fields.
      if not result:
        format = '{ascdate:S} {asctime:S} {levelno:d} {levelname:S} ' \
                 '{filename:S}:{lineno:d} {message}'
        result = parse(format, message)
        if result:
          result['asctime'] = result['asc_date'] + 'T' + result['asctime'] + 'Z'

      # If we managed to parse, put it into a dict to send
      if result:
        record = {
          'asctime': result['asctime'],
          'levelno': result['levelno'],
          'levelname': result['levelname'],
          'message': result['message']
        }
      else:
        logging.info('Failed to parse: "%s"', message)
        record = {'message': message}

      logging.debug('Sending stderr to CDS: field: %s, record: %s',
                    field_name, record)
      # Send the record off the the data server
      self._write_record_to_data_server(field_name, json.dumps(record))


    # Start of actual _read_and_send_logger_stderr() code.
    if configs is None:
      configs = self.supervisor.running_configs()

    stderr_results = self.supervisor.read_stderr(configs)

    for config, stderr_lines in stderr_results.items():
      # Alert the data server of our latest status. Note: if we've
      # loaded a new file, logger and config may have disappeared, in
      # which case we punt.
      logger = self.config_to_logger.get(config, None)
      if not logger:
        continue

      field_name = 'stderr:logger:' + logger

      # Messages may be multiple lines. We're going to assume that
      # each one starts with an ISO8601 time string. If a line doesn't
      # begin with one, assume it's a continuation of the previous
      # message. Aggregate in a list until we see the next time string
      # or run out of input.
      message = []
      for line in stderr_lines.split('\n'):
        if not line:
          continue

        # If line begins with a time string, assume, it's a new message
        # and previous message is complete. Send off the old one.
        try:
          datetime.datetime.strptime(line.split('T')[0], '%Y-%m-%d')
          has_timestamp = True
        except ValueError:
          has_timestamp = False
        if has_timestamp:
          parse_and_send_message(field_name, '\n'.join(message))
          message = []
        message.append(line)

      # Send the last straggler
      if message:
        parse_and_send_message(field_name, '\n'.join(message))

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
  supervisor_group.add_argument('--start_supervisor_in',
                                dest='start_supervisor_in', action='store',
                                default=None,
                                help='Start local copy of '
                                'supervisord, building its own config file '
                                'in a temporary file. Note that if we start '
                                'our own supervisor, it and the loggers will '
                                'exit when we do. If we use an external '
                                'instance, the loggers will continue to in '
                                'whatever state they were last in after we '
                                'exit.')

  supervisor_group.add_argument('--supervisor_logger_config',
                                dest='supervisor_logger_config',
                                default=None, action='store',
                                help='Location of file where an existing '
                                'supervisord process should look for logger '
                                'process definitions. Mutually exclusive with '
                                '--start_supervisor_in.')
  parser.add_argument('--supervisor_host', dest='supervisor_host',
                      action='store', type=str, default='*',
                      help='Hostname at which supervisor should serve. "*" '
                      'means "any" and will allow remote connections.')
  parser.add_argument('--supervisor_port', dest='supervisor_port',
                      action='store', type=int, default=DEFAULT_SUPERVISOR_PORT,
                      help='Host port at which supervisor should serve.')
  parser.add_argument('--supervisor_logfile_dir',
                      dest='supervisor_logfile_dir', action='store',
                      default=DEFAULT_SUPERVISOR_LOGFILE_DIR,
                      help='Directory where supervisor and logger '
                      'stderr/stdout will be written.')
  parser.add_argument('--supervisor_auth',
                      dest='supervisor_auth', action='store', default=None,
                      help='If provided, a username:password string to be '
                      'used to authenticate to the supervisor instance. If '
                      'omitted, no auth will be assumed.')

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
  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

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

  if args.supervisor_auth and not ':' in args.supervisor_auth:
    logging.fatal('Arg --supervisor_auth must be of form "username:password"')
    sys.exit(1)
  supervisor = SupervisorConnector(
    start_supervisor_in=args.start_supervisor_in,
    supervisor_logger_config=args.supervisor_logger_config,
    supervisor_host=args.supervisor_host,
    supervisor_port=args.supervisor_port,
    supervisor_logfile_dir=args.supervisor_logfile_dir,
    supervisor_auth=args.supervisor_auth,
    group='logger',
    max_tries=args.max_tries,
    log_level=log_level)

  ############################
  # Create our LoggerManager
  logger_manager = LoggerManager(
    api=api, supervisor=supervisor,
    data_server_websocket=args.data_server_websocket,
    supervisor_logfile_dir=args.supervisor_logfile_dir,
    interval=args.interval,
    logger_log_level=logger_log_level)

  # When told to quit, shut down gracefully
  api.on_quit(callback=logger_manager.quit)

  # When an active config changes in the database, update our configs here
  api.on_update(callback=logger_manager._update_configs)

  # When new configs are loaded, update our file of config processes
  api.on_load(callback=logger_manager._build_new_config_file)

  ############################
  # Start all the various LoggerManager threads running
  logger_manager.start()

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
      except (FileNotFoundError, PermissionError):
        pass
      atexit.register(readline.write_history_file, hist_path)

      command_line_reader = ServerAPICommandLine(api=api)
      command_line_reader.run()

  except KeyboardInterrupt:
    pass
  logging.debug('Done with logger_manager.py - exiting')

  # Ask our SupervisorConnector to shutdown.
  if supervisor:
    supervisor.shutdown()
