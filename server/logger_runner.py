#!/usr/bin/env python3
"""Low-level class to run a logger config in its own process and write
its stderr to a file.

Can be run from the command line as follows:
```
   server/logger_runner.py \
     --config test/NBP1406/NBP1406_cruise.yaml:gyr1->net \
     --stderr_file /var/log/openrvdas/gyr1.stderr
```

But its main intended use is to be invoked by another module to start
a logger in its own, non-blocking process:
```
    runner = LoggerRunner(config=config, name=logger,
                          stderr_file=stderr_file,
                          logger_log_level=self.logger_log_level)
    self.logger_runner_map[logger] = runner
    self.logger_runner_map[logger].start()
```
Simulated Serial Ports:

The NBP1406_cruise.yaml file above specifies configs that read from
simulated serial ports and write to UDP port 6224. To get the configs
to actually run, you'll need to run

```
  logger/utils/simulate_data.py --config test/NBP1406/simulate_NBP1406.yaml
```
in a separate terminal window to create the virtual serial ports the
sample config references and feed simulated data through them.)

To verify that the scripts are actually working as intended, you can
create a network listener on port 6224 in yet another window:
```
  logger/listener/listen.py --network :6224
```
"""
import logging
import multiprocessing
import pprint
import signal
import sys
import time

from importlib import reload
from logging.handlers import RotatingFileHandler
from setproctitle import setproctitle

# Add the openrvdas/ directory to module search path
from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))
from logger.utils.read_config import read_config  # noqa: E402
from logger.utils.stderr_logging import DEFAULT_LOGGING_FORMAT  # noqa: E402
from logger.listener.listen import ListenerFromLoggerConfig  # noqa: E402

# For writing to cached data server
from logger.transforms.to_das_record_transform import ToDASRecordTransform  # noqa: E402
from logger.writers.cached_data_writer import CachedDataWriter  # noqa: E402
from logger.writers.composed_writer import ComposedWriter  # noqa: E402
from logger.utils.stderr_logging import StdErrLoggingHandler  # noqa: E402

# Rotate stderr logs out so that their sizes remain manageable. Plan to keep all
# stderr logs, but don't swamp if something goes awry. Note: these values
# should probably be extracted to a settings.py file somewhere.
STDERR_MAX_BYTES = 1000000  # 10M
STDERR_BACKUP_COUNT = 100  # 100 backups should be plenty


################################################################################
def kill_handler(self, signum):
    """Translate an external signal (such as we'd get from os.kill) into a
    KeyboardInterrupt, which will signal the start() loop to exit nicely."""
    logging.info('Received external kill')
    raise KeyboardInterrupt('Received external kill signal')


################################################################################
def config_from_filename(filename):
    """Load a logger configuration from a filename. If there's a ':' in
    the config file name, then we expect what is before the colon to be
    a cruise definition, and what is after to be the name of a
    configuration inside that definition.
    """
    config_name = None
    if filename.find(':') > 0:
        (filename, config_name) = filename.split(':', maxsplit=1)
    config = read_config(filename)

    if config_name:
        config_dict = config.get('configs')
        if not config_dict:
            raise ValueError('Configuration name "%s" specified, but no '
                             '"configs" section found in file "%s"'
                             % (config_name, filename))
        config = config_dict.get(config_name)
        if not config:
            raise ValueError('Configuration name "%s" not found in file "%s"'
                             % (config_name, filename))
    logging.info('Loaded config file: %s', pprint.pformat(config))
    return config


################################################################################
def config_is_runnable(config):
    """Is this logger configuration runnable? (Or, e.g. does it just have
    a name and no readers/transforms/writers?)
    """
    if not config:
        return False
    return 'readers' in config or 'writers' in config


################################################################################
def run_logger(logger, config, stderr_filename=None, stderr_data_server=None,
               log_level=logging.INFO):
    """Run a logger, sending its stderr to a cached data server if so indicated

    logger -    Name of logger

    config -    Config dict

    stderr_filename  - If not None, send stderr to this file.

    stderr_data_server  - If not None, host:port of cached data server to
                send stderr messages to.

    log_level - Level at which logger should be logging (e.g logging.WARNING,
                logging.INFO, etc.
    """
    # Reset logging to its freshly-imported state
    reload(logging)

    if stderr_filename:
        stderr_handlers = [RotatingFileHandler(stderr_filename,
                                               maxBytes=STDERR_MAX_BYTES,
                                               backupCount=STDERR_BACKUP_COUNT)]
    else:
        stderr_handlers = []
    logging.basicConfig(
        handlers=stderr_handlers,
        level=log_level,
        format=DEFAULT_LOGGING_FORMAT)

    if stderr_data_server:
        field_name = 'stderr:logger:' + logger
        cds_writer = ComposedWriter(
            transforms=ToDASRecordTransform(data_id='stderr', field_name=field_name),
            writers=CachedDataWriter(data_server=stderr_data_server))
        logging.getLogger().addHandler(StdErrLoggingHandler(cds_writer))

    # Set the name of the process for ps
    config_name = config.get('name', 'no_name')
    setproctitle('openrvdas/server/logger_runner.py:' + config_name)
    logging.info(f'Starting logger {logger} config {config_name}')

    try:
        if config_is_runnable(config):
            listener = ListenerFromLoggerConfig(config=config)
            try:
                listener.run()
            except KeyboardInterrupt:
                logging.warning(f'Received quit for {config_name}')
    except Exception as e:
        logging.fatal(e)

    # Allow a moment for stderr_writers to finish up
    time.sleep(0.25)


################################################################################
class LoggerRunner:
    ############################
    def __init__(self, config, name=None, stderr_filename=None,
                 stderr_data_server=None, logger_log_level=logging.WARNING):
        """Create a LoggerRunner.
        ```
        config   - Python dict containing the logger configuration to be run

        name     - Optional name to give to logger process.

        stderr_filename - Optional name of file to write stderr to.

        stderr_data_server - Optional host:port of a cached data server to
                   send encoded stderr messages to.

        logger_log_level - At what logging level our logger should operate.
        ```
        """
        self.config = config
        self.name = name or config.get('name', 'Unnamed logger')
        self.stderr_filename = stderr_filename
        self.stderr_data_server = stderr_data_server
        self.logger_log_level = logger_log_level

        self.process = None     # this is hold the logger process
        self.failed = False     # flag - has logger failed?
        self.quit_flag = False  # flag - has quit been signaled?

        # Set the signal handler so that an external break will get
        # translated into a KeyboardInterrupt. But signal only works if
        # we're in the main thread - catch if we're not, and just assume
        # everything's gonna be okay and we'll get shut down with a proper
        # "quit()" call otherwise.
        try:
            signal.signal(signal.SIGTERM, kill_handler)
        except ValueError:
            logging.debug('LoggerRunner not running in main thread; '
                          'shutting down with Ctl-C may not work.')

    ############################
    def start(self):
        """Start a listener subprocess."""
        self.quit_flag = False
        self.failed = False

        # We're going to go ahead and create the process, even if the
        # config is not runnable, just so we can get log messages that the
        # config has been started.

        # If config is not runnable, just say so and be done with it.
        # if not self.is_runnable():
        #  logging.info('Process %s is complete. Not running.', self.name)
        #  return

        run_logger_kwargs = {
            'logger': self.name,
            'config': self.config,
            'stderr_filename': self.stderr_filename,
            'stderr_data_server': self.stderr_data_server,
            'log_level': self.logger_log_level
        }
        self.process = multiprocessing.Process(target=run_logger,
                                               kwargs=run_logger_kwargs,
                                               daemon=True)
        self.process.start()

    ############################
    def is_runnable(self):
        """Is this logger configuration runnable? (Or, e.g. does it just have
        a name and no readers/transforms/writers?)
        """
        return config_is_runnable(self.config)

    ############################
    def is_alive(self):
        """Is the logger in question alive?"""
        return self.process and self.process.is_alive()

    ############################
    def is_failed(self):
        """Return whether the logger has failed."""
        return self.failed

    ############################
    def quit(self):
        """Signal loop exit and send termination signal to process."""
        self.quit_flag = True
        if self.process:
            self.process.terminate()
            self.process.join()
        self.process = None
        self.failed = False


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', dest='config', action='store', required=True,
                        help='Logger configuration to run. May either be the '
                        'name of a file containing a single logger configuration '
                        'or filename:config_name, for a file containing a cruise '
                        'definition followed by the name of the specific '
                        'configuration inside that definition.')

    parser.add_argument('--name', dest='name', action='store', default=None,
                        help='Name to give to logger process.')

    parser.add_argument('--stderr_filename', dest='stderr_filename', default=None,
                        help='Optional filename to which stderr should be '
                        'written. Will attempt to create path if it does not '
                        'exist.')

    parser.add_argument('--stderr_data_server', dest='stderr_data_server', default=None,
                        help='Optional host:port of a cached data server to which '
                        ' stderr messages should be written.')

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
    logging.basicConfig(format=DEFAULT_LOGGING_FORMAT)
    logging.getLogger().setLevel(log_level)

    # What level do we want our component loggers to write?
    logger_log_level = LOG_LEVELS[min(args.logger_verbosity, max(LOG_LEVELS))]

    config = config_from_filename(args.config)

    # Finally, create our runner and run it
    runner = LoggerRunner(config=config,
                          name=args.name,
                          stderr_filename=args.stderr_filename,
                          stderr_data_server=args.stderr_data_server,
                          logger_log_level=logger_log_level)
    runner.start()

    # Wait for it to complete
    runner.process.join()
