#!/usr/bin/env python3
"""
"""
import json
import logging
import os
import parse
import pprint
import signal
import sys
import time
import threading

from os.path import dirname, realpath; sys.path.append(dirname(dirname(realpath(__file__))))

from logger.utils.stderr_logging import DEFAULT_LOGGING_FORMAT
from logger.utils.read_config import read_config
from logger.utils.das_record import DASRecord
from logger.readers.text_file_reader import TextFileReader
from logger.transforms.to_das_record_transform import ToDASRecordTransform
from logger.writers.file_writer import FileWriter
from logger.writers.text_file_writer import TextFileWriter
from logger.writers.cached_data_writer import CachedDataWriter
from logger.writers.composed_writer import ComposedWriter

from logger.listener.listener import Listener
from server.logger_runner import LoggerRunner

################################################################################
class LoggerSupervisor:
  """Given a map of logger:config, make sure the relevant configs are
  running for the relevant loggers."""
  def __init__(self, configs=None, stderr_filebase=None,
               cds_host_port=None, max_tries=3, min_uptime=10,
               interval=1, logger_log_level=logging.WARNING):
    """
    ```
    configs   - dict of {logger_name: config} that are to be run

    stderr_filebase - Path/filebase to which stderr messages for each
               logger should be written. Enables relaying logger
               stderr to cached data server.

    cds_host_port - Optional host:port to which status message should be
               sent to a cached data server

    max_tries - number of times to try a dead logger config. If zero, then
                never stop retrying.

    min_uptime - How many seconds a logger must be up to count as having been
                 successfully started and reset max_tries.

    interval - How many seconds between checks that a logger is still running.

    logger_log_level - at what system log level the logger should log (if
                it were a woodchuck chucking wood)
    ```
    """
    self.configs = configs or {}
    self.stderr_filebase = stderr_filebase
    self.cds_host_port = cds_host_port
    self.max_tries = max_tries
    self.min_uptime = min_uptime
    self.interval = interval
    self.logger_log_level = logger_log_level

    self.data_server_writer = None
    if cds_host_port:
      self.data_server_writer = CachedDataWriter(data_server=cds_host_port)

    # Where we store the map from logger name to config actually
    # running. Also map from logger name to LoggerRunner that's doing
    # the actual work.
    self.logger_config_map = {}
    self.logger_runner_map = {}

    self.logger_stderr_file_map = {}       # logger: stderr_file
    self.logger_stderr_file_thread = {}    # logger: thread running listener
    self.logger_map_lock = threading.Lock()

    # When each logger was last restarted, and how many times it has
    # failed shortly after start so we know when to give up.
    self.logger_last_started = {}
    self.logger_restart_counts = {}

    self.quit_flag = False

  ###################
  def run(self):
    if self.configs:
      self.update_configs()

    while not self.quit_flag:
      self._check_loggers()
      time.sleep(self.interval)

  ###################
  def quit(self):
    self.quit_flag = True

    with self.logger_map_lock:
      loggers = set(self.logger_runner_map)
      for logger in loggers:
        self._delete_logger(logger)

  ###################
  def _check_loggers(self):
    logging.info('Checking loggers...')
    status = {}
    with self.logger_map_lock:
      for logger, runner in self.logger_runner_map.items():
        if not runner.is_runnable():
          logging.info('%s - okay; not runnable', logger)
          continue

        if runner.is_alive():
          logging.info('%s - okay; running', logger)
          continue

        if runner.is_failed():
          logging.info('%s - failed', logger)
          continue

        # If we're here, runner is runnable is not running, and hasn't
        # yet been labeled as a failed logger.
        logging.warning('%s unexpectedly dead.', logger)

        # How long has it been since we've restarted? If a long enough
        # time has passed, give it a clean slate.
        last_started = self.logger_last_started.get(logger, 0)
        restart_count = self.logger_restart_counts.get(logger, 0)
        if time.time() - last_started < self.min_uptime:
          restart_count += 1
        else:
          restart_count = 0
        self.logger_restart_counts[logger] = restart_count

        # If we've restarted too many times recently, declare the
        # logger failed and move on.
        if restart_count >= self.max_tries:
          runner.failed = True
          logging.warning('%s has failed %s times; not restarting',
                          logger, restart_count)
          continue

        # If here, we're going to try restarting.
        logging.info('%s - restarting', logger)
        self.logger_last_started[logger] = time.time()
        runner.start()

  ##############################################################################
  def _stderr_file_to_cds(self, logger):
    """Iteratively read from a file (presumed to be a logger's stderr file
    and send the lines to a cached data server labeled as coming from
    stderr:logger:<logger>.

    Format of error messages is as a JSON-encoded dict of asctime, levelno,
    levelname, filename, lineno and message.

    To be run in a separate thread from _start_logger()

    ONLY CALL THIS FROM WITHIN _start_logger FOR THREAD SAFETY
    """

    if not self.data_server_writer:
      logging.error('INTERNAL ERROR: called _stder_file_to_cds(), but no '
                    'cached data server defined?!?')
      return

    stderr_file = self.logger_stderr_file_map[logger]
    field_name = 'stderr:logger:'+logger
    cds_host_port = self.cds_host_port
    logging.warning('Starting read %s: %s -> %s',
                    logger, stderr_file, cds_host_port)

    message_format = ('{ascdate:S} {asctime:S} {levelno:d} {levelname:w} '
                      '{filename:w}.py:{lineno:d} {message}')

    # Loop here until the file we're looking for actually exists
    while not os.path.isfile(stderr_file):
      logging.debug('Logfile %s does not exist yet', stderr_file)
      time.sleep(1)
    logging.warning('Logfile %s now exists!!!!', stderr_file)
      
    reader = TextFileReader(file_spec=stderr_file, tail=True)
    
    transform = ToDASRecordTransform(field_name=field_name)

    while logger in self.logger_runner_map:
      record = reader.read()
      try:
        parsed_fields = parse.parse(message_format, record)
        fields = {'asctime': (parsed_fields['ascdate'] + 'T' +
                              parsed_fields['asctime']),
                  'levelno': parsed_fields['levelno'],
                  'levelname': parsed_fields['levelname'],
                  'filename': parsed_fields['filename'] + '.py',
                  'lineno': parsed_fields['lineno'],
                  'message': parsed_fields['message']
        }
        das_record = DASRecord(fields={field_name: json.dumps(fields)})
        logging.warning('Message: %s', fields)
        self.data_server_writer.write(das_record)
      except KeyError:
        logging.warning('Couldn\'t parse stderr message: %s', record)

  ###################
  def _start_logger(self, logger, config):
    """ONLY CALL THIS FROM WITHIN update_configs for thread safety."""
    config_name = config.get('name', logger + '_config')
    logging.warning('Called _start_logger for %s: %s', logger, config_name)

    self.logger_config_map[logger] = config
    stderr_file = self.stderr_filebase + logger + '.stderr'
    self.logger_stderr_file_map[logger] = stderr_file

    runner = LoggerRunner(config=config, name=config_name,
                          stderr_file=stderr_file,
                          logger_log_level=self.logger_log_level)
    self.logger_runner_map[logger] = runner
    self.logger_runner_map[logger].start()

    # If we don't already have a thread listening on this file and
    # sending its contents to the cached data server, start one now.
    if not logger in self.logger_stderr_file_thread:
      thread = threading.Thread(name=logger+'_stderr_read',
                                target=self._stderr_file_to_cds,
                                kwargs={'logger': logger},
                                daemon=True)
      thread.start()
      self.logger_stderr_file_thread[logger] = thread

  ###################
  def _delete_logger(self, logger):
    """ONLY CALL THIS FROM WITHIN update_configs for thread safety."""
    runner = self.logger_runner_map.get(logger)
    if not runner:
      logging.warning('Stale logger %s not found?!?', logger)
      return
    logging.warning('Waiting for logger %s to complete', logger)
    runner.quit()

    del self.logger_config_map[logger]
    del self.logger_runner_map[logger]

    # Shut down the listener waiting for output
    #logging.warning('Waiting for status writer for %s to terminate.', logger)
    #self.logger_stderr_file_thread[logger].join()
    #logging.warning('Terminated.')
    #del self.logger_stderr_file_thread[logger]
    del self.logger_stderr_file_map[logger]
    logging.warning('Logger %s has terminated', logger)

  ###################
  def update_configs(self, configs=None):
    """Receive a new map of logger:config and start/stop loggers as
    necessary.
    """
    configs = configs or self.configs
    if not configs:
      logging.warning('No logger configs to run!')

    with self.logger_map_lock:
      stale_loggers = set(self.logger_config_map) - set(configs)
      new_loggers =  set(configs) - set(self.logger_config_map)
      other_loggers = set(self.logger_config_map) - stale_loggers - new_loggers

      logging.debug('Stale: %s', stale_loggers)
      logging.debug('New: %s', new_loggers)
      logging.debug('Other: %s', other_loggers)

      # Find and shut down loggers that don't exist in our new configs
      for logger in stale_loggers:
        logging.info('Shutting down logger %s.', logger)
        self._delete_logger(logger)

      # Add new loggers that have first appeared in our new config and
      # start them up.
      for new_logger in new_loggers:
        new_config = configs[new_logger]
        logging.info('Starting new logger %s with %s.', new_logger,
                     new_config.get('name', 'no_name'))
        self._start_logger(new_logger, new_config)

      # For existing loggers, see whether their configs have
      # changed. If so stop and restart with new config.  start them
      # up.
      for logger in other_loggers:
        new_config = configs[logger]
        old_config = self.logger_config_map[logger]
        if new_config == old_config:
          logging.debug('Config for %s unchanged.', logger)
          continue

        logging.info('Updating %s from %s to %s', logger,
                     old_config.get('name', 'no_name'),
                     new_config.get('name', 'no_name'))
        self._delete_logger(logger)
        self._start_logger(logger, new_config)


"""
      status = {
        'config': config_name,
        'errors': errors,
        'running': running,
        'failed': logger in self.failed_loggers,
        'pid': process.pid if process else None
      }
"""

################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('--config', dest='config', action='store', required=True,
                      help='Initial set of configs to run.')

  parser.add_argument('--stderr_filebase', dest='stderr_filebase',
                      default='/var/tmp/openrvdas/',
                      help='Path/filebase to which stderr messages '
                      'for each logger should be written. Enables relaying '
                      'logger stderr to cached data server.')

  parser.add_argument('--cds_host_port', dest='cds_host_port', default=None,
                      help='Host:port of cached data server to which '
                        'stderr messages should be sent.')

  parser.add_argument('--max_tries', dest='max_tries', action='store',
                      type=int, default=3, help='How many times to try a '
                      'crashing config before giving up on it as failed. If '
                      'zero, then never stop retrying.')

  parser.add_argument('--min_uptime', dest='min_uptime', action='store',
                      type=float, default=60, help='How many seconds a logger '
                      'must be up to count as having been successfully '
                      'started and reset max_tries.')

  parser.add_argument('--interval', dest='interval', action='store',
                      type=float, default=1, help='How many seconds between '
                      'checks that a logger is still running.')

  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')

  parser.add_argument('-V', '--logger_verbosity', dest='logger_verbosity',
                      default=0, action='count',
                      help='Increase output verbosity of component loggers')


  parser.add_argument('--mode', dest='mode', required=True,
                      help='Cruise mode to select')

  args = parser.parse_args()

  # Set up logging first of all

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  log_level = LOG_LEVELS[min(args.verbosity, max(LOG_LEVELS))]
  logging.basicConfig(format=DEFAULT_LOGGING_FORMAT, level=log_level)

  # What level do we want our component loggers to write?
  logger_log_level = LOG_LEVELS[min(args.logger_verbosity, max(LOG_LEVELS))]

  config = read_config(args.config)

  mode_config_names = config.get('modes').get(args.mode)
  all_configs = config.get('configs')
  mode_configs = {logger: all_configs.get(mode_config_names[logger])
                  for logger in mode_config_names}
  sup = LoggerSupervisor(configs=mode_configs,
                         stderr_filebase=args.stderr_filebase,
                         cds_host_port=args.cds_host_port,
                         max_tries=args.max_tries,
                         min_uptime=args.min_uptime,
                         interval=args.interval,
                         logger_log_level=logger_log_level
  )
  sup.run()
