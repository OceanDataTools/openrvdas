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
optionally include 'prefix', 'eol', 'timestamp' and 'time_format'
keys:

############# Gyro ###############
  gyro:
    class: UDP
    timestamp: true
    prefix: gyro
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
import subprocess
import sys
import threading
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
from logger.readers.logfile_reader import LogfileReader  # noqa: E402
from logger.writers.text_file_writer import TextFileWriter  # noqa: E402
from logger.writers.udp_writer import UDPWriter  # noqa: E402

from logger.utils.read_config import read_config  # noqa: E402
from logger.utils.timestamp import TIME_FORMAT  # noqa: E402


class SimUDP:
    """Open a network port and feed stored logfile data to it."""
    ############################

    def __init__(self, port, filebase=None, record_format=None,
                 time_format=TIME_FORMAT, eol='\n'):
        """
        ```
        port -  UDP port on which to write records.

        time_format - What format to use for timestamp

        filebase - Prefix string to be matched (with a following "*") to find
                   files to be used. e.g. /tmp/log/NBP1406/knud/raw/NBP1406_knud

        record_format
                     If specified, a custom record format to use for extracting
                     timestamp and record. The default is '{timestamp:ti} {record}'
        ```
        """
        self.port = port
        self.time_format = time_format
        self.filebase = filebase
        self.record_format = record_format or '{timestamp:ti} {record}'
        self.compiled_record_format = parse.compile(self.record_format)

        # Do we have any files we can actually read from?
        if not glob.glob(filebase + '*'):
            logging.warning('No files matching "%s*"', filebase)
            self.quit_flag = True
            return

        self.reader = LogfileReader(filebase=filebase, use_timestamps=True,
                                    record_format=self.record_format,
                                    time_format=self.time_format)
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
                if not record:
                    if not loop or self.first_time:
                        break
                    logging.info('Looping instrument %s', self.prefix)
                    self.reader = LogfileReader(filebase=self.filebase,
                                                record_format=self.record_format,
                                                use_timestamps=True)
                    continue

                # We've now got a record. Try parsing timestamp off it
                try:
                    parsed_record = self.compiled_record_format.parse(record).named
                    record = parsed_record['record']

                # We had a problem parsing. Discard record and try reading next one.
                except (KeyError, ValueError, AttributeError):
                    logging.warning('Unable to parse record into "%s"', self.record_format)
                    logging.warning('Record: %s', record)
                    continue

                if not record:
                    continue

                self.writer.write(record)
                self.first_time = False

        except (OSError, KeyboardInterrupt):
            self.quit_flag = True

        logging.info('Finished %s', self.prefix)

################################################################################


class SimSerial:
    """Create a virtual serial port and feed stored logfile data to it."""
    ############################

    def __init__(self, port, time_format=TIME_FORMAT, filebase=None,
                 record_format=None, eol='\n',
                 baudrate=9600, bytesize=8, parity='N', stopbits=1,
                 timeout=None, xonxoff=False, rtscts=False, write_timeout=None,
                 dsrdtr=False, inter_byte_timeout=None, exclusive=None):
        """
        Simulate a serial port, feeding it data from the specified file.

        ```
        port - Temporary serial port to create and make available for reading
               records.

        filebase     Possibly wildcarded string specifying files to be opened.

        record_format
                     If specified, a custom record format to use for extracting
                     timestamp and record. The default is '{timestamp:ti} {record}'.

        time_format - What format to use for timestamp
        ```
        """
        # We'll create two virtual ports: 'port' and 'port_in'; we will write
        # to port_in and read the values back out from port
        self.read_port = port
        self.write_port = port + '_in'
        self.time_format = time_format
        self.filebase = filebase
        self.record_format = record_format or '{timestamp:ti} {record}'
        self.compiled_record_format = parse.compile(self.record_format)
        self.serial_params = None

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

        # Finally, find path to socat executable
        self.socat_path = None
        for socat_path in ['/usr/bin/socat', '/usr/local/bin/socat']:
            if os.path.exists(socat_path) and os.path.isfile(socat_path):
                self.socat_path = socat_path
        if not self.socat_path:
            raise NameError('Executable "socat" not found on path. Please refer '
                            'to installation guide to install socat.')

    ############################
    def _run_socat(self):
        """Internal: run the actual command."""
        verbose = '-d'
        write_port_params = 'pty,link=%s,raw,echo=0' % self.write_port
        read_port_params = 'pty,link=%s,raw,echo=0' % self.read_port

        cmd = [self.socat_path,
               verbose,
               # verbose,   # repeating makes it more verbose
               read_port_params,
               write_port_params,
               ]
        try:
            # Run socat process using Popen, checking every second or so whether
            # it's died (poll() != None) or we've gotten a quit signal.
            logging.info('Calling: %s', ' '.join(cmd))
            socat_process = subprocess.Popen(cmd)
            while not self.quit and not socat_process.poll():
                try:
                    socat_process.wait(1)
                except subprocess.TimeoutExpired:
                    pass

        except Exception as e:
            logging.error('ERROR: socat command: %s', e)

        # If here, process has terminated, or we've seen self.quit. We
        # want both to be true: if we've terminated, set self.quit so that
        # 'run' loop can exit. If self.quit, terminate process.
        if self.quit:
            socat_process.kill()
        else:
            self.quit = True
        logging.info('Finished: %s', ' '.join(cmd))

    ############################
    def run(self, loop=False):
        # If self.serial_params is None, it means that either read or
        # write device already exist, so we shouldn't actually run, or
        # we'll destroy them.
        if not self.serial_params:
            return

        """Create the virtual port with socat and start feeding it records from
        the designated logfile. If loop==True, loop when reaching end of input."""
        self.socat_thread = threading.Thread(target=self._run_socat, daemon=True)
        self.socat_thread.start()
        time.sleep(0.2)

        self.reader = LogfileReader(filebase=self.filebase, use_timestamps=True,
                                    record_format=self.record_format, time_format=self.time_format)

        self.writer = TextFileWriter(self.write_port, truncate=True)

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
                                                time_format=self.time_format)

                # We've now got a record. Try parsing timestamp off it
                try:
                    parsed_record = self.compiled_record_format.parse(record).named
                    record = parsed_record['record']

                # We had a problem parsing. Discard record and try reading next one.
                except (KeyError, ValueError, AttributeError):
                    logging.warning('Unable to parse record into "%s"', self.record_format)
                    logging.warning('Record: %s', record)
                    continue

                if not record:
                    continue

                logging.debug('SimSerial writing: %s', record)
                self.writer.write(record)   # and write it to the virtual port
            except (OSError, KeyboardInterrupt):
                break

        # If we're here, we got None from our input, and are done. Signal
        # for run_socat to exit
        self.quit = True


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

    parser.add_argument('--no_loop', dest='no_loop', action='store_true',
                        help='If True, don\'t loop when reaching end of '
                        'sample data')

    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(message)s'
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

            # Save class of simulator, and remove it from the config dict
            inst_class = config['class']
            del config['class']

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

        logging.warning('Running simulated ports for %s', ', '.join(configs.keys()))

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
                                  record_format=args.record_format)
        # Is it a UDP port?
        elif args.udp:
            simulator = SimUDP(port=args.udp,
                               time_format=args.time_format,
                               filebase=args.filebase,
                               record_format=args.record_format)
        else:
            parser.error('If --filebase specified, must also specify either --serial '
                         'or --udp.')

        # Run it
        simulator.run(loop)
