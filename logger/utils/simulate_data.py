#!/usr/bin/env python3
"""Simulate a live data feed by sending stored logger data to
specified UDP ports and/or simulated (temporary) serial ports.

May either be invoked for a single data feed with command line
options, or by specifying a YAML-format configuration file that sets
up multiple feeds at once.

To invoke a single data feed:

   simulate_data.py --udp 5501 --filebase /data/2019-05-11/raw/GYRO

will read timestamped lines from files matching /data/2019-05-11/raw/GYRO*
and broadcast them via UDP port 5501:

$HEHDT,087.1,T*21
$HEHDT,087.1,T*21
$HEHDT,087.1,T*21
$HEHDT,087.1,T*21

By default, the reader assumes that the log file record format is
"{timestamp:ti} {record}" but if, for example, the timestamp has a different
format, or a different separator is used between the timestamp and record,
the default may be overridden with the --record_format argument. E.g. if a
comma is used as the delimiter between timestamp and record:

2019-11-28T01:01:38.762221Z,$HEHDT,087.1,T*21
2019-11-28T01:01:38.953182Z,$HEHDT,087.1,T*21

you may specify

   simulate_data.py --udp 6224 \
     --filebase test/NBP1406/gyr1/raw/NBP1406_gyr1-2014-08-01 \
     --record_format '{timestamp:ti},{record}'

Unless --no-loop is specified on the command line, the system will
rewind to the beginning of all log files when it reaches the end of
its input.

Instead of --udp, you may also specify --serial (and optionally
--baudrate) to simulate a serial port:

   simulate_data.py --serial /tmp/ttyr05 --filebase /data/2019-05-11/raw/GYRO

If --config is specified

   simulate_data.py --config data/2019-05-11/simulate_config.yaml

the script will expect a YAML file keyed by instrument names, where
each instrument name references a dict including keys 'class' (Serial
or UDP), 'port' (e.g. 5501 or /tmp/ttyr05) and 'filebase'. It may
optionally include 'eol', 'timestamp' and 'time_format'
keys:

############# Gyro ###############
  gyro:
    class: UDP
    timestamp: true
    eol: \r
    port: 56332
    filebase: /data/2019-05-11/raw/GYRO

############# Fluorometer ###############
fluorometer:
  class: Serial
  port: /tmp/ttyr04
  baudrate: 9600
  filebase: /data/2019-05-11/raw/FLUOROMETER

Note that if class is 'Serial', it may also include the full range of
serial port options:

    baudrate: 9600
    bytesize: 8
    parity: N
    stopbits: 1
    timeout: false
    xonxoff: false
    rtscts: false,
    write_timeout: false
    dsrdtr: false
    inter_byte_timeout: false
    exclusive: false

"""
import glob
import logging
import os.path
import parse
import pty
import sys
import threading

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
from logger.readers.logfile_reader import LogfileReader  # noqa: E402
from logger.writers.udp_writer import UDPWriter  # noqa: E402

from logger.utils.read_config import read_config  # noqa: E402
from logger.utils.timestamp import TIME_FORMAT  # noqa: E402


class SimUDP:
    """Open a network port and feed stored logfile data to it."""
    ############################

    def __init__(self, port, name=None, filebase=None, record_format=None,
                 time_format=TIME_FORMAT, eol='\n', input_eol=None, quiet=False):
        """
        ```
        port -  UDP port on which to write records.

        name -  Optional user-friendly name to display on warning messages

        filebase - Prefix string to be matched (with a following "*") to find
                   files to be used. e.g. /tmp/log/NBP1406/knud/raw/NBP1406_knud

        record_format
                     If specified, a custom record format to use for extracting
                     timestamp and record. The default is '{timestamp:ti} {record}'

        time_format - What format to use for timestamp

        eol - String to append to end of an output record

        input_eol - Optional string by which to recognize the end of a record
        ```
        """
        self.port = port
        self.name = name
        self.time_format = time_format
        self.filebase = filebase
        self.record_format = record_format or '{timestamp:ti} {record}'
        self.compiled_record_format = parse.compile(self.record_format)
        self.eol = eol
        self.input_eol = input_eol
        self.quiet=quiet

        # Do we have any files we can actually read from?
        if not glob.glob(filebase + '*'):
            logging.warning('No files matching "%s*"', filebase)
            self.quit_flag = True
            return

        self.reader = LogfileReader(filebase=filebase, use_timestamps=True,
                                    record_format=self.record_format,
                                    time_format=self.time_format,
                                    eol=self.input_eol, quiet=self.quiet)
        self.writer = UDPWriter(port=port, eol=eol)

        self.first_time = True
        self.quit_flag = False

    ############################
    def run(self, loop=False):
        """Start reading and writing data. If loop==True, loop when reaching
        end of input.
        """
        logging.info('Starting %s: %s', self.port, self.filebase)
        try:
            while not self.quit_flag:
                record = self.reader.read()

                # If we don't have a record, we're (probably) at the end of
                # the file. If it's the first time we've tried reading, it
                # means we probably didn't get a usable file. Either break out
                # (if we're not looping, or if we don't have a usable file),
                # or start reading from the beginning (if we are looping and
                # have a usable file).
                if record is None:
                    if not loop or self.first_time:
                        break
                    logging.info('Looping instrument %s', self.filebase)
                    self.reader = LogfileReader(filebase=self.filebase,
                                                record_format=self.record_format,
                                                use_timestamps=True,
                                                eol=self.input_eol,
                                                quiet=self.quiet)
                    continue

                # We've now got a record. Try parsing timestamp off it
                try:
                    parsed_record = self.compiled_record_format.parse(record).named
                    record = parsed_record['record']

                # We had a problem parsing. Discard record and try reading next one.
                except (KeyError, ValueError, AttributeError):
                    logging.warning('%s: Unable to parse record into "%s"',
                                    self.name, self.record_format)
                    logging.warning('Record: "%s"', record)
                    continue

                if not record:
                    continue

                self.writer.write(record)
                self.first_time = False

        except (OSError, KeyboardInterrupt):
            self.quit_flag = True

        logging.info('Finished %s', self.filebase)


################################################################################
class SimSerial:
    """Create a virtual serial port and feed stored logfile data to it."""
    ############################

    def __init__(self, port, name=None, time_format=TIME_FORMAT, filebase=None,
                 record_format=None, eol='\n', input_eol=None,
                 baudrate=9600, bytesize=8, parity='N', stopbits=1,
                 timeout=None, xonxoff=False, rtscts=False, write_timeout=None,
                 dsrdtr=False, inter_byte_timeout=None, exclusive=None,
                 quiet=False):
        """
        Simulate a serial port, feeding it data from the specified file.

        ```
        port - Temporary serial port to create and make available for reading
               records.

        name -  Optional user-friendly name to display on warning messages

        time_format - What format to use for timestamp

        filebase     Possibly wildcarded string specifying files to be opened.

        record_format
                     If specified, a custom record format to use for extracting
                     timestamp and record. The default is '{timestamp:ti} {record}'.

        eol - String by which to recognize the end of a record

        input_eol - Optional string by which to recognize the end of a record
        ```
        """
        # We'll create two virtual ports: 'port' and 'port_in'; we will write
        # to port_in and read the values back out from port
        self.read_port = port
        self.write_port = port + '_in'
        self.name = name
        self.time_format = time_format
        self.filebase = filebase
        self.record_format = record_format or '{timestamp:ti} {record}'
        self.compiled_record_format = parse.compile(self.record_format)
        self.eol = eol
        self.input_eol = input_eol
        self.serial_params = None
        self.quiet = quiet

        # Complain, but go ahead if read_port or write_port exist.
        for path in [self.read_port, self.write_port]:
            if os.path.exists(path):
                logging.warning('Path %s exists; overwriting!', path)

        # Do we have any files we can actually read from?
        if not glob.glob(filebase + '*'):
            logging.warning('No files matching "%s*"', filebase)
            return

        # Set up our parameters
        self.serial_params = {'baudrate': baudrate,
                              'byteside': bytesize,
                              'parity': parity,
                              'stopbits': stopbits,
                              'timeout': timeout,
                              'xonxoff': xonxoff,
                              'rtscts': rtscts,
                              'write_timeout': write_timeout,
                              'dsrdtr': dsrdtr,
                              'inter_byte_timeout': inter_byte_timeout,
                              'exclusive': exclusive}
        self.quit = False

    ############################
    def run(self, loop=False):
        # If self.serial_params is None, it means that either read or
        # write device already exist, so we shouldn't actually run, or
        # we'll destroy them.
        if not self.serial_params:
            return

        try:
            # Create simulated serial port (something like /dev/ttys2), and link
            # it to the port they want to connect to (like /tmp/tty_s330).
            write_fd, read_fd = pty.openpty()     # open the pseudoterminal
            true_read_port = os.ttyname(read_fd)  # this is the true filename of port

            # Get rid of any previous symlink if it exists, and symlink the new pty
            try:
                os.unlink(self.read_port)
            except FileNotFoundError:
                pass
            os.symlink(true_read_port, self.read_port)

            self.reader = LogfileReader(filebase=self.filebase, use_timestamps=True,
                                        record_format=self.record_format,
                                        time_format=self.time_format,
                                        eol=self.input_eol, quiet=self.quiet)
            logging.info('Starting %s: %s', self.read_port, self.filebase)
            while not self.quit:
                try:
                    record = self.reader.read()  # get the next record
                    logging.debug('SimSerial got: %s', record)

                    # End of input? If loop==True, re-open the logfile from the start
                    if record is None:
                        if not loop:
                            break

                        self.reader = LogfileReader(filebase=self.filebase,
                                                    use_timestamps=True,
                                                    record_format=self.record_format,
                                                    time_format=self.time_format,
                                                    eol=self.input_eol, quiet=self.quiet)

                    # We've now got a record. Try parsing timestamp off it
                    logging.debug(f'Read record: "{record}"')
                    try:
                        parsed_record = self.compiled_record_format.parse(record).named
                        record = parsed_record['record']

                    # We had a problem parsing. Discard record and try reading next one.
                    except (KeyError, ValueError, TypeError, AttributeError):
                        logging.warning('%s: Unable to parse record into "%s"',
                                        self.name, self.record_format)
                        logging.warning('Record: "%s"', record)
                        continue

                    if not record:
                        continue

                    logging.debug('SimSerial writing: %s', record)
                    os.write(write_fd, (record + self.eol).encode('utf8'))

                except (OSError, KeyboardInterrupt):
                    break

            # If we're here, we got None from our input, and are done. Signal
            # for run_socat to exit
            self.quit = True

        finally:
            # Get rid of the symlink we've created
            os.unlink(self.read_port)


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument('--config', dest='config', default=None,
                        help='Config file of JSON specs for port-file mappings.')

    parser.add_argument('--serial', dest='serial',
                        help='Virtual serial port to open')
    parser.add_argument('--baud', dest='baud', type=int,
                        help='Optional baud rate for serial port.')

    parser.add_argument('--udp', dest='udp', type=int,
                        help='UDP port to broadcast on')

    parser.add_argument('--time_format', dest='time_format', default=TIME_FORMAT,
                        help='Format string for parsing timestamp')

    parser.add_argument('--filebase', dest='filebase',
                        help='Basename of logfiles to read from. A "*" will be '
                        'appended to this string and all matching files will '
                        'be read in order.')

    parser.add_argument('--record_format', dest='record_format',
                        default='{timestamp:ti} {record}',
                        help='If specified, a custom record format to use for extracting '
                        'timestamp and record. The default is {timestamp:ti} {record}')

    parser.add_argument('--loop', dest='loop', action='store_true', default=True,
                        help='If True, loop when reaching end of sample data')

    parser.add_argument('--quiet', dest='quiet', action='store_true', default=True,
                        help='If True, silently ignore unparseable records')

    parser.add_argument('--no_loop', dest='no_loop', action='store_true',
                        help='If True, don\'t loop when reaching end of '
                        'sample data')

    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(lineno)d %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    # Default is to loop unless told otherwise
    loop = args.loop and not args.no_loop

    # Have we been given a config file?
    if args.config:
        configs = read_config(args.config)
        logging.info('Read configs: %s', configs)
        thread_list = []
        for inst, config in configs.items():
            if 'class' not in config:
                logging.warning('No class definition for config "%s"', inst)
                continue

            # Stash name of config
            config['name'] = inst
            # Save class of simulator, and remove it from the config dict
            inst_class = config['class']
            del config['class']

            # Fold in some things from the command line, if they're
            # not specified in the config itself.
            if 'time_format' not in config:
                config['time_format'] = args.time_format
            if 'record_format' not in config:
                config['record_format'] = args.record_format
            if 'quiet' not in config:
                config['quiet'] = args.quiet

            # Create the appropriate simulator with the config
            if inst_class == 'Serial':
                writer = SimSerial(**config)
            elif inst_class == 'UDP':
                writer = SimUDP(**config)
            else:
                logging.error('Unknown class for config %s', inst_class)
                logging.error('Acceptable classes are "Serial" and "UDP"')
                continue

            writer_thread = threading.Thread(target=writer.run, kwargs={'loop': loop},
                                             name=inst, daemon=True)
            writer_thread.start()
            thread_list.append(writer_thread)

        logging.info('Running simulated ports for %s', ', '.join(configs.keys()))

        try:
            for thread in thread_list:
                thread.join()
            logging.warning('All processes have completed - exiting')
        except KeyboardInterrupt:
            logging.warning('Keyboard interrupt - exiting')
            pass

    # If no config file, just a simple, single source, create and run a
    # single simulator.
    else:
        if not args.filebase:
            parser.error('Either --config or --filebase must be specified')

        # Is it a serial port?
        if args.serial:
            simulator = SimSerial(port=args.serial,
                                  time_format=args.time_format,
                                  baudrate=args.baud,
                                  filebase=args.filebase,
                                  record_format=args.record_format,
                                  quiet=args.quiet)
        # Is it a UDP port?
        elif args.udp:
            simulator = SimUDP(port=args.udp,
                               time_format=args.time_format,
                               filebase=args.filebase,
                               record_format=args.record_format,
                               quiet=args.quiet)
        else:
            parser.error('If --filebase specified, must also specify either --serial '
                         'or --udp.')

        # Run it
        simulator.run(loop)
