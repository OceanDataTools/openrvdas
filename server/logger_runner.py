#!/usr/bin/env python3
"""Low-level class to run a logger config in its own process, capturing
the process's stderr and relaying it to a file and/or a callback.

Can be run from the command line as follows:
```
   server/logger_runner.py \
     --config test/NBP1406/NBP1406_cruise.yaml:gyr1->net \
     --stderr_filename /var/log/openrvdas/gyr1.stderr
```

But its main intended use is to be invoked by another module (such as
server/logger_manager.py) to start a logger in its own, non-blocking
process:
```
    runner = LoggerRunner(config=config, name=logger,
                          stderr_filename=stderr_filename,
                          stderr_callback=my_callback,
                          logger_log_level=self.logger_log_level)
    runner.start()
```

The logger itself is run via 'python -m logger.listener.listen
--config_file ...' as a true subprocess, with its stderr (fd 2)
captured by a pipe. A relay thread in the parent reads the pipe and
fans each line out to a rotating stderr file and/or the passed
stderr_callback. This way the parent - not the (possibly dying) child -
is responsible for delivering the child's diagnostics: messages written
just before a crash survive in the pipe and are still read and
delivered after the child has exited.

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
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading

from logging.handlers import RotatingFileHandler

from logger.utils.read_config import read_config  # noqa: E402
from logger.utils.stderr_logging import DEFAULT_LOGGING_FORMAT  # noqa: E402

# Rotate stderr logs out so that their sizes remain manageable. Plan to keep all
# stderr logs, but don't swamp if something goes awry. Note: these values
# should probably be extracted to a settings.py file somewhere.
STDERR_MAX_BYTES = 1000000  # 1M per file
STDERR_BACKUP_COUNT = 100  # 100 backups should be plenty

# Directory from which 'python -m logger.listener.listen' is runnable
OPENRVDAS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


################################################################################
def kill_handler(signum, frame):
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
    logging.info('Loaded config file: %s', filename)
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
class LoggerRunner:
    ############################
    def __init__(self, config, name=None, stderr_filename=None,
                 stderr_callback=None, death_callback=None,
                 logger_log_level=logging.WARNING):
        """Create a LoggerRunner.
        ```
        config   - Python dict containing the logger configuration to be run

        name     - Optional name to give to logger process.

        stderr_filename - Optional name of file to write the logger's stderr
                   to. Will be rotated when it exceeds STDERR_MAX_BYTES.

        stderr_callback - Optional function to call with each line of the
                   logger's stderr as it is received. Lines are passed as
                   str, without trailing newline.

        death_callback - Optional function to call (with this LoggerRunner
                   as its single argument) when the process dies
                   unexpectedly. Called from the stderr relay thread when
                   the stderr pipe hits EOF and the process has been
                   reaped - i.e. after the process's last words have been
                   delivered. Not called for deliberate quit() shutdowns.

        logger_log_level - At what logging level our logger should operate.
        ```
        If neither stderr_filename nor stderr_callback are specified, the
        logger's stderr will be echoed to our own stderr.
        """
        self.config = config
        self.name = name or config.get('name', 'Unnamed logger')
        self.stderr_filename = stderr_filename
        self.stderr_callback = stderr_callback
        self.death_callback = death_callback
        self.logger_log_level = logger_log_level

        self.process = None     # the subprocess.Popen running the logger
        self.failed = False     # flag - has logger failed?
        self.quit_flag = False  # flag - has quit been signaled?

        self.config_file_path = None  # temp file we pass to listen.py
        self.stderr_relay_thread = None

        # Handler that writes the (already-formatted) stderr lines we
        # receive from the child to a rotating file. delay=True so we don't
        # create the file until there's something to write.
        if stderr_filename:
            self.stderr_file_handler = RotatingFileHandler(
                stderr_filename, maxBytes=STDERR_MAX_BYTES,
                backupCount=STDERR_BACKUP_COUNT, delay=True)
            # Lines arrive already formatted by the child; pass them through.
            self.stderr_file_handler.setFormatter(logging.Formatter('%(message)s'))
        else:
            self.stderr_file_handler = None

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
        """Start the logger in its own subprocess, with stderr captured."""
        self.quit_flag = False
        self.failed = False

        # If config is not runnable, don't bother starting a process.
        if not self.is_runnable():
            logging.info('Config for %s is not runnable; not starting.', self.name)
            return

        # Write the config out where listen.py can read it. JSON is a
        # subset of YAML, so read_config can parse it. Reuse the file on
        # restarts; it's cleaned up in quit().
        if not self.config_file_path:
            config_name = self.config.get('name', self.name)
            prefix = 'openrvdas_' + config_name.replace(os.sep, '_') + '_'
            (fd, self.config_file_path) = tempfile.mkstemp(prefix=prefix,
                                                           suffix='.yaml')
            with os.fdopen(fd, 'w') as config_file:
                json.dump(self.config, config_file)

        cmd = [sys.executable, '-m', 'logger.listener.listen',
               '--config_file', self.config_file_path]
        if self.logger_log_level <= logging.DEBUG:
            cmd += ['-v', '-v']
        elif self.logger_log_level <= logging.INFO:
            cmd += ['-v']

        logging.info('Starting logger %s: %s', self.name, ' '.join(cmd))
        self.process = subprocess.Popen(cmd, stderr=subprocess.PIPE,
                                        cwd=OPENRVDAS_ROOT)

        # Read and deliver the child's stderr until EOF (i.e. until the
        # child exits).
        self.stderr_relay_thread = threading.Thread(
            name=self.name + '_stderr_relay',
            target=self._stderr_relay, args=(self.process,), daemon=True)
        self.stderr_relay_thread.start()

    ############################
    def _stderr_relay(self, process):
        """Read lines of the child process's stderr until EOF and fan each
        one out to our stderr file and/or callback. Run in its own thread;
        EOF means the child has exited.
        """
        for line_bytes in iter(process.stderr.readline, b''):
            line = line_bytes.decode('utf-8', errors='replace').rstrip('\n')
            self._handle_stderr_line(line)
        process.stderr.close()

        # EOF means every copy of the child's stderr write fd has been
        # closed - almost always because the child has exited. Reap it; if
        # it is somehow still running with a closed stderr, don't report a
        # death.
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logging.warning('Logger %s closed its stderr but is still '
                            'running?', self.name)
            return
        logging.debug('Logger %s stderr relay got EOF; child has exited.',
                      self.name)

        # By this point the child's last words have been delivered, so an
        # immediate restart can't clobber them. Don't report deliberate
        # shutdowns.
        if self.death_callback and not self.quit_flag:
            self.death_callback(self)

    ############################
    def _handle_stderr_line(self, line):
        """Deliver one line of the child's stderr to file and/or callback;
        if we have neither, echo it to our own stderr."""
        if self.stderr_file_handler:
            record = logging.LogRecord(name=self.name, level=logging.INFO,
                                       pathname='', lineno=0, msg=line,
                                       args=(), exc_info=None)
            self.stderr_file_handler.handle(record)

        if self.stderr_callback:
            try:
                self.stderr_callback(line)
            except Exception as e:
                logging.debug('Error in stderr callback for %s: %s',
                              self.name, e)

        if not self.stderr_file_handler and not self.stderr_callback:
            print(line, file=sys.stderr)

    ############################
    def is_runnable(self):
        """Is this logger configuration runnable? (Or, e.g. does it just have
        a name and no readers/transforms/writers?)
        """
        return config_is_runnable(self.config)

    ############################
    def is_alive(self):
        """Is the logger in question alive?"""
        return self.process is not None and self.process.poll() is None

    ############################
    def is_failed(self):
        """Return whether the logger has failed."""
        return self.failed

    ############################
    def quit(self):
        """Signal loop exit and try to cleanly terminate the process."""
        self.quit_flag = True
        if self.process:
            # First attempt: terminate gracefully
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Escalation: send SIGKILL
                self.process.kill()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # If it's *still* alive, warn, and just live with the
                    # undead process
                    logging.error('Process %d could not be killed',
                                  self.process.pid)

        # Let the relay thread drain whatever stderr the child wrote
        # before dying, then clean up.
        if self.stderr_relay_thread:
            self.stderr_relay_thread.join(timeout=5)
            self.stderr_relay_thread = None
        if self.stderr_file_handler:
            self.stderr_file_handler.close()
        if self.config_file_path:
            try:
                os.unlink(self.config_file_path)
            except OSError:
                pass
            self.config_file_path = None

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
                        help='Optional filename to which the logger\'s stderr '
                        'should be written.')

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
    name = args.name or config.get('name', 'logger')

    # If asked to forward stderr to a cached data server, do it from
    # here - the parent - via a callback, rather than from inside the
    # logger process.
    stderr_callback = None
    if args.stderr_data_server:
        from logger.utils.das_record import DASRecord
        from logger.writers.cached_data_writer import CachedDataWriter
        cds_writer = CachedDataWriter(data_server=args.stderr_data_server)

        def cds_stderr_callback(line):
            cds_writer.write(DASRecord(data_id='stderr',
                                       fields={'stderr:logger:' + name: line}))
        stderr_callback = cds_stderr_callback

    # Finally, create our runner and run it
    runner = LoggerRunner(config=config,
                          name=name,
                          stderr_filename=args.stderr_filename,
                          stderr_callback=stderr_callback,
                          logger_log_level=logger_log_level)
    runner.start()

    # Wait for it to complete
    try:
        if runner.process:
            runner.process.wait()
    except KeyboardInterrupt:
        runner.quit()
