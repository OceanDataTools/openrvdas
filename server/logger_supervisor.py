#!/usr/bin/env python3
"""
"""
import logging
import sys
import time
import threading

from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))
from logger.utils.stderr_logging import DEFAULT_LOGGING_FORMAT  # noqa: E402
from logger.utils.read_config import read_config  # noqa: E402

from server.logger_runner import LoggerRunner  # noqa: E402


################################################################################
class LoggerSupervisor:
    """Given a map of {logger:config}, start the configs and make sure
   they keep running.
    """

    def __init__(self, configs=None, stderr_file_pattern=None,
                 max_tries=3, min_uptime=10, interval=1,
                 logger_log_level=logging.WARNING):
        """
        ```
        configs   - dict of {logger_name: config} that are to be run

        stderr_file_pattern - Pattern into which logger name will be interpolated
                   to create the file path/name to which the logger's stderr
                   will be written. E.g. '/var/log/openrvdas/{logger}.stderr'

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
        self.stderr_file_pattern = stderr_file_pattern
        self.max_tries = max_tries
        self.min_uptime = min_uptime
        self.interval = interval
        self.logger_log_level = logger_log_level

        # Where we store the map from logger name to config actually  # noqa: E402
        # running. Also map from logger name to LoggerRunner that's doing  # noqa: E402
        # the actual work.
        self.logger_config_map = {}
        self.logger_runner_map = {}
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

    ###################
    def _start_logger(self, logger, config):
        """ONLY CALL THIS FROM WITHIN update_configs for thread safety."""
        config_name = config.get('name', logger + '_config')
        logging.info('Called start_logger for %s: %s', logger, config_name)

        self.logger_config_map[logger] = config
        stderr_file = self.stderr_file_pattern.format(logger=logger)

        runner = LoggerRunner(config=config, name=logger,
                              stderr_file=stderr_file,
                              logger_log_level=self.logger_log_level)
        self.logger_runner_map[logger] = runner
        self.logger_runner_map[logger].start()

    ###################

    def _delete_logger(self, logger):
        """ONLY CALL THIS FROM WITHIN update_configs for thread safety."""
        runner = self.logger_runner_map.get(logger)
        if not runner:
            logging.warning('Stale logger %s not found?!?', logger)
            return
        logging.info('Waiting for logger %s to complete', logger)
        runner.quit()

        del self.logger_config_map[logger]
        del self.logger_runner_map[logger]

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
            new_loggers = set(configs) - set(self.logger_config_map)
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

    ###################

    def get_status(self):
        """Return a dict of the current config name and current run status of
        each logger in the form, e.g.:

        {'s330': {'config':'s330->net', 'status':'RUNNING'},
         'gyr1': {'config':'gyr1->file', 'status':'FAILED'},
        }

        Possible status are EXITED, RUNNING, FAILED and STARTING. EXITED
        is the status when a logger is not 'runnable' - e.g. the 'off'
        config.  STARTING is used when a runner is runnable but is not
        running and is not FAILED - i.e. we haven't given up on it.
        """
        logger_status = {}
        with self.logger_map_lock:
            for logger, runner in self.logger_runner_map.items():

                logger_config = self.logger_config_map[logger]
                config_name = logger_config.get('name', 'no name')

                if not runner.is_runnable():
                    status = 'EXITED'
                elif runner.is_alive():
                    status = 'RUNNING'
                elif runner.is_failed():
                    status = 'FAILED'
                else:
                    status = 'STARTING'
                logger_status[logger] = {'config': config_name, 'status': status}
        return logger_status


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', dest='config', action='store', required=True,
                        help='Initial set of configs to run.')

    parser.add_argument('--stderr_file_pattern', dest='stderr_file_pattern',
                        default='/var/log/openrvdas/{logger}.stderr',
                        help='Pattern into which logger name will be '
                        'interpolated to create the file path/name to which '
                        'the logger\'s stderr will be written. E.g. '
                        '\'/var/log/openrvdas/{logger}.stderr\'')

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

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
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
                           stderr_file_pattern=args.stderr_file_pattern,
                           max_tries=args.max_tries,
                           min_uptime=args.min_uptime,
                           interval=args.interval,
                           logger_log_level=logger_log_level
                           )
    sup.run()
