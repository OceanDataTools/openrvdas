#!/usr/bin/env python3
"""Instantiates and runs the Listener class. Try
```
  listen.py --help
```
for details.

Examples:
  ```
  logger/listener/listen.py \
    --logfile test/NBP1700/s330/raw/NBP1700_s330 \
    --interval 0.25 \
    --transform_slice 1: \
    --transform_timestamp \
    --transform_prefix s330 \
    --write_file -
  ```
(Reads lines from the Seapath300 sample logfiles every 0.25 seconds,
strips the old timestamps off, prepends a new one, then the prefix
's330', then writes the result to stdout.)
  ```
  logger/listener/listen.py \
    --config_file test/configs/simple_logger.yaml
  ```
(Instantiates logger from config file that says to read from the
project's LICENSE file, prepend a timestamp and the string "license:"
and writ to stdout every 0.2 seconds.)

The listen.py script is essentially a form of 'cat' on steroids,
reading records from files, serial or network ports, modifying what it
receives, then writing it back out to somewhere else.

For fun, you can even run listen.py as an Ouroboros script, feeding it on its
own output:
```
  echo x > tmp
  listen.py --file tmp --prefix p --write_file tmp --tail --interval 1 -v -v
```
"""
import argparse
import importlib
import logging
import pprint
import re
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.cached_data_reader import CachedDataReader  # noqa: E402
from logger.readers.logfile_reader import LogfileReader  # noqa: E402
from logger.readers.network_reader import NetworkReader  # noqa: E402
from logger.readers.tcp_reader import TCPReader
from logger.readers.udp_reader import UDPReader  # noqa: E402
from logger.readers.redis_reader import RedisReader  # noqa: E402
from logger.readers.serial_reader import SerialReader  # noqa: E402
from logger.readers.text_file_reader import TextFileReader  # noqa: E402
from logger.readers.database_reader import DatabaseReader  # noqa: E402
from logger.readers.composed_reader import ComposedReader  # noqa:E402,F401

from logger.transforms.extract_field_transform import ExtractFieldTransform  # noqa: E402
from logger.transforms.nmea_transform import NMEATransform  # noqa: E402
from logger.transforms.prefix_transform import PrefixTransform  # noqa: E402
from logger.transforms.regex_filter_transform import RegexFilterTransform  # noqa: E402
from logger.transforms.qc_filter_transform import QCFilterTransform  # noqa: E402
from logger.transforms.slice_transform import SliceTransform  # noqa: E402
from logger.transforms.timestamp_transform import TimestampTransform  # noqa: E402
from logger.transforms.parse_nmea_transform import ParseNMEATransform  # noqa: E402
from logger.transforms.parse_transform import ParseTransform  # noqa: E402
from logger.transforms.xml_aggregator_transform import XMLAggregatorTransform  # noqa: E402

from logger.transforms.max_min_transform import MaxMinTransform  # noqa: E402
from logger.transforms.from_json_transform import FromJSONTransform  # noqa: E402
from logger.transforms.to_json_transform import ToJSONTransform  # noqa: E402
from logger.transforms.to_das_record_transform import ToDASRecordTransform  # noqa: E402
from logger.transforms.count_transform import CountTransform  # noqa: E402
from logger.transforms.true_winds_transform import TrueWindsTransform  # noqa: E402,F401

# Compute and emit various NMEA strings
from logger.writers.network_writer import NetworkWriter  # noqa: E402
from logger.writers.tcp_writer import TCPWriter
from logger.writers.udp_writer import UDPWriter  # noqa: E402
from logger.writers.serial_writer import SerialWriter  # noqa: E402
from logger.writers.redis_writer import RedisWriter  # noqa: E402
from logger.writers.file_writer import FileWriter  # noqa: E402
from logger.writers.text_file_writer import TextFileWriter  # noqa: E402, F401
from logger.writers.logfile_writer import LogfileWriter  # noqa: E402
from logger.writers.database_writer import DatabaseWriter  # noqa: E402
from logger.writers.record_screen_writer import RecordScreenWriter  # noqa: E402
from logger.writers.cached_data_writer import CachedDataWriter  # noqa: E402
from logger.writers.influxdb_writer import InfluxDBWriter  # noqa: E402,F401
from logger.writers.composed_writer import ComposedWriter  # noqa: E402,F401

from logger.utils import read_config, timestamp, nmea_parser, record_parser  # noqa: E402
from logger.utils.stderr_logging import StdErrLoggingHandler, STDERR_FORMATTER  # noqa: E402

from logger.listener.listener import Listener  # noqa: E402


################################################################################
class ListenerFromLoggerConfig(Listener):
    """Helper class for instantiating a Listener object from a Python dict."""
    ############################

    def __init__(self, config, log_level=None):
        """Create a Listener from a Python config dict."""

        if not type(config) is dict:
            raise ValueError('ListenerFromLoggerConfig expects config of type '
                             '"dict" but received one of type "%s": %s'
                             % (type(config), str(config)))

        # Extract keyword args from config and instantiate.
        logging.debug('ListenerFromLoggerConfig instantiating logger '
                      'config: %s', pprint.pformat(config))
        try:
            kwargs = self._kwargs_from_config(config)
        except ValueError as e:
            config_name = config.get('name', 'unknown logger')
            raise ValueError('Config for %s: %s' % (config_name, e))

        super().__init__(**kwargs)

    ############################
    def _kwargs_from_config(self, config_dict):
        """Parse a kwargs from a JSON string, making exceptions for keywords
        'readers', 'transforms', and 'writers' as internal class references."""
        if not config_dict:
            return {}

        if not type(config_dict) is dict:
            raise ValueError('Received config dict of type "%s" (instead of dict)'
                             % type(config_dict))

        # First we pull out the 'stderr_writers' spec as a special case so
        # that we can catch and properly route stderr output from
        # parsing/creation of the other keyword args.
        kwargs = {}
        stderr_writers_spec = config_dict.get('stderr_writers', None)
        if stderr_writers_spec:
            stderr_writers = self._class_kwargs_from_config(stderr_writers_spec)
            logging.getLogger().addHandler(StdErrLoggingHandler(stderr_writers))

            # We've already initialized the logger for stderr_writers, so
            # *don't* pass that arg on, or things will get logged twice.
            del config_dict['stderr_writers']

        for key, value in config_dict.items():
            # Declaration of readers, transforms and writers. Note that the
            # singular "reader" is a special case for TimeoutReader that
            # takes a single reader.
            if key in ['readers', 'reader', 'transforms', 'writers', 'writer']:
                if not value:
                    raise ValueError('declaration of "%s" in class has no kwargs?!?' % key)
                kwargs[key] = self._class_kwargs_from_config(value)

            # If value is a simple float/int/string/etc, just add to keywords
            elif value is None or type(value) in [float, bool, int, str, list, dict]:
                kwargs[key] = value

            # Else what do we have?
            else:
                raise ValueError('unexpected key:value in configuration: '
                                 '{}: {}'.format(key, str(value)))
        return kwargs

    ############################
    def _class_kwargs_from_config(self, class_json):
        """Parse a class's kwargs from a JSON string."""
        if not type(class_json) in [list, dict]:
            raise ValueError('class_kwargs_from_config expected dict or list; '
                             'got: "{}"'.format(class_json))

        # If we've got a list, recurse on each element
        if type(class_json) is list:
            return [self._class_kwargs_from_config(c) for c in class_json]

        # Get name and constructor for component we're going to instantiate
        class_name = class_json.get('class', None)
        if class_name is None:
            raise ValueError('missing "class" definition in "{}"'.format(class_json))

        # Are they telling us where the class definition is? If so import it
        class_module_name = class_json.get('module', None)
        if class_module_name is not None:
            module = importlib.import_module(class_module_name)
            class_const = getattr(module, class_name, None)
            if not class_const:
                raise ValueError('No component class "{}" found in module "{}"'.format(
                    class_name, class_module_name))
        else:
            # If they haven't given us a 'module' declaration, assume class
            # is something that's already defined.
            class_const = globals().get(class_name, None)
            if not class_const:
                raise ValueError('No component class "{}" found: "{}"'.format(
                    class_name, class_json))

        # Get the keyword args for the component
        kwarg_dict = class_json.get('kwargs', {})
        try:
            kwargs = self._kwargs_from_config(kwarg_dict)
        except (ValueError, RuntimeError) as e:
            raise ValueError('Class "%s": %s' % (class_name, e))

        if not kwargs:
            logging.debug('No kwargs found for component {}'.format(class_name))

        # Instantiate!
        logging.debug('Instantiating {}({})'.format(class_name, kwargs))
        try:
            component = class_const(**kwargs)
        except (TypeError, ValueError, RuntimeError) as e:
            raise ValueError('Class {}: {}\nClass definition: {}'.format(
                class_name, e, pprint.pformat(class_json)))
        return component


################################################################################
class ListenerFromLoggerConfigString(ListenerFromLoggerConfig):
    """Helper class for instantiating a Listener object from a JSON/YAML string"""
    ############################

    def __init__(self, config_str, log_level=None):
        """Create a Listener from a JSON config string."""
        config = read_config.parse(config_str)
        logging.info('Received config string: %s', pprint.pformat(config))
        super().__init__(config=config)


################################################################################
class ListenerFromLoggerConfigFile(ListenerFromLoggerConfig):
    """Helper class for instantiating a Listener object from a JSON config."""
    ############################

    def __init__(self, config_file, config_name=None, log_level=None):
        """Create a Listener from a Python config file. If the file name
        format is file_name:config, then assume the file_name is that of a
        cruise definition, and look for the config itself under the
        'configs:' key of the file's YAML.
        """
        # If they've got a ':' in the config file name, then we're
        # expecting them to also give us a config name to look for.
        if config_file.find(':') > 0:
            (config_file, config_name) = config_file.split(':', maxsplit=1)
        config = read_config.read_config(config_file)

        if config_name:
            config_dict = config.get('configs', None)
            if not config_dict:
                raise ValueError('Configuration name "%s" specified, but no '
                                 '"configs" section found in file "%s"'
                                 % (config_name, config_file))
            config = config_dict.get(config_name, None)
            if not config:
                raise ValueError('Configuration name "%s" not found in file "%s"'
                                 % (config_name, config_file))

        logging.info('Loaded config file: %s', pprint.pformat(config))
        super().__init__(config=config)


################################################################################
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        epilog='Note that arguments are parsed and applied IN ORDER, so if you '
        'want a flag like --tail to be applied to a reader, or --slice_separator '
        'to be applied to --transform_slice, it must appear before that reader on '
        'the command line. Similarly, transforms will be added to the queue and '
        'applied in the order they appear on the command line; multiple '
        'specifications of a reader, writer or transform will result in multiple '
        'instances of it being created. Trust us, that\'s a feature.'
    )

    ############################
    # Set up from config file
    parser.add_argument('--config_file', dest='config_file', default=None,
                        help='Read Listener configuration from YAML/JSON file. '
                        'If argument contains a colon, it will be interpreted '
                        'as cruise_def_file_name:logger_config, and the script '
                        'will look for a logger config name under the file\'s '
                        '"configs" section. '
                        'If specified, no other command line arguments (except '
                        '-v) are allowed.')

    parser.add_argument('--config_string', dest='config_string', default=None,
                        help='Read Listener configuration from YAML/JSON string. '
                        'If specified, no other command line arguments (except '
                        '-v) are allowed.')

    ############################
    # Readers
    parser.add_argument('--network', dest='network', default=None,
                        help='Comma-separated network addresses to read from.  '
                        'NOTE: This has been REPLACED by --udp and --tcp.')

    parser.add_argument('--tcp', dest='tcp', default=None,
                        help='Comma-separated tcp address to read from, '
                        'where an address is of format [source:]port[,...] and '
                        'source, when provided, is the address of the '
                        'interface you want to listen on.  NOTE: This replaces '
                        'the old --network argument.')

    parser.add_argument('--udp', dest='udp', default=None,
                        help='Comma-separated udp addresses to read from, '
                        'where an address is of format [source:]port[,...] and '
                        'source, when provided, is either the address of the '
                        'interface you want to listen on, or a multicast '
                        'group.  NOTE: This replaces the old --network argument.')

    parser.add_argument('--database', dest='database', default=None,
                        help='Format: user@host:database:field1,field2,... '
                        'Read specified fields from database. If no fields are '
                        'specified, read all fields in database. Should '
                        'be accompanied by the --database_password flag.')

    parser.add_argument('--file', dest='file', default=None,
                        help='Comma-separated files to read from in parallel. '
                        'Note that wildcards in a filename will be expanded, '
                        'and the resulting files read sequentially. A single '
                        'dash (\'-\') will be interpreted as stdout.')

    parser.add_argument('--logfile', dest='logfile', default=None,
                        help='Comma-separated logfile base filenames to read '
                        'from in parallel. Logfile dates will be added '
                        'automatically.')

    parser.add_argument('--logfile_use_timestamps', dest='logfile_use_timestamps',
                        action='store_true', default=False,
                        help='Make LogfileReaders deliver records at intervals '
                        'corresponding to the intervals indicated by the stored '
                        'record timestamps.')

    parser.add_argument('--cached_data', dest='cached_data_server', default=None,
                        help='Read from cached data server with argument '
                        'field_1,field2,...[@host:port]. Defaults to '
                        'localhost:8766.')

    parser.add_argument('--redis', dest='redis', default=None,
                        help='Redis pubsub channel[@host[:port]] to read from. '
                        'Defaults to localhost:6379.')

    parser.add_argument('--serial', dest='serial', default=None,
                        help='Comma-separated serial port spec containing at '
                        'least port=[port], but also optionally baudrate, '
                        'timeout, max_bytes and/or other SerialReader '
                        'parameters.')

    parser.add_argument('--interval', dest='interval', type=float, default=0,
                        help='Number of seconds between reads')

    parser.add_argument('--tail', dest='tail',
                        action='store_true', default=False, help='Do not '
                        'exit after reading file EOF; continue to check for '
                        'additional input.')

    parser.add_argument('--refresh_file_spec', dest='refresh_file_spec',
                        action='store_true', default=False, help='When at EOF '
                        'and --tail is specified, check for new matching files '
                        'that may have appeared since our last attempt to read.')

    ############################
    # Transforms
    parser.add_argument('--transform_prefix', dest='prefix', default='',
                        help='Prefix each record with this string')

    parser.add_argument('--transform_nmea', dest='nmea', action='store_true',
                        default=False, help='Build NMEA-formatted sentence from '
                        'data fields')

    parser.add_argument('--transform_timestamp', dest='timestamp',
                        action='store_true', default=False,
                        help='Timestamp each record as it is read')

    parser.add_argument('--transform_slice', dest='slice', default='',
                        help='Return only the specified (space-separated) '
                        'fields of a text record. Can be comma-separated '
                        'integer values and/or ranges, e.g. "1,3,5:7,-1". '
                        'Note: zero-base indexing, so "1:" means "start at '
                        'second element.')

    parser.add_argument('--slice_separator', dest='slice_separator', default=' ',
                        help='Field separator for --slice.')

    parser.add_argument('--transform_regex_filter', dest='regex_filter',
                        default='',
                        help='Only pass records containing this regex.')

    parser.add_argument('--transform_extract', dest='extract',
                        default='', help='Extract the named field from '
                        'passed DASRecord or data dict.')

    parser.add_argument('--transform_qc_filter', dest='qc_filter',
                        default='', help='Pass nothing unless the fields in the '
                        'received DASRecord exceed comma-separated '
                        '<field_name>:<lower>:<upper> bounds.')

    parser.add_argument('--transform_parse_nmea', dest='parse_nmea',
                        action='store_true', default=False,
                        help='Convert tagged, timestamped NMEA records into '
                        'Python DASRecords.')
    parser.add_argument('--parse_nmea_message_path',
                        dest='parse_nmea_message_path',
                        default=nmea_parser.DEFAULT_MESSAGE_PATH,
                        help='Comma-separated globs of NMEA message definition '
                        'file names, e.g. '
                        'local/message/*.yaml')
    parser.add_argument('--parse_nmea_sensor_path',
                        dest='parse_nmea_sensor_path',
                        default=nmea_parser.DEFAULT_SENSOR_PATH,
                        help='Comma-separated globs of NMEA sensor definition '
                        'file names, e.g. '
                        'local/sensor/*.yaml')
    parser.add_argument('--parse_nmea_sensor_model_path',
                        dest='parse_nmea_sensor_model_path',
                        default=nmea_parser.DEFAULT_SENSOR_MODEL_PATH,
                        help='Comma-separated globs of NMEA sensor model '
                        'definition file names, e.g. '
                        'local/sensor_model/*.yaml')

    parser.add_argument('--transform_parse', dest='parse',
                        action='store_true', default=False,
                        help='Convert tagged, records into dict of values (or'
                        'JSON or DASRecords if --parse_to_json or '
                        '--parse_to_das_record are specified).')
    parser.add_argument('--parse_definition_path',
                        dest='parse_definition_path',
                        default=record_parser.DEFAULT_DEFINITION_PATH,
                        help='Comma-separated globs of device definition '
                        'file names, e.g. '
                        'local/devices/*.yaml')
    parser.add_argument('--parse_to_json',
                        dest='parse_to_json', action='store_true',
                        help='If specified, parser outputs JSON.')
    parser.add_argument('--parse_to_das_record',
                        dest='parse_to_das_record', action='store_true',
                        help='If specified, parser outputs DASRecords.')

    parser.add_argument('--time_format', dest='time_format',
                        default=timestamp.TIME_FORMAT,
                        help='Format in which to expect time strings.')

    parser.add_argument('--transform_aggregate_xml', dest='aggregate_xml',
                        default='', help='Aggregate records of XML until a '
                        'completed XML record whose outer element matches '
                        'the specified tag has been seen, then pass it along '
                        'as a single record.')

    parser.add_argument('--transform_max_min', dest='max_min',
                        action='store_true', default=False,
                        help='Return only values that exceed the '
                        'previously-seen max or min for a field, annotated by '
                        'the name "field:max" or "field:min".')

    parser.add_argument('--transform_count', dest='count',
                        action='store_true', default=False,
                        help='Return the count of number of times fields in '
                        'the passed record have been seen, annotated by '
                        'the name "field:count".')

    parser.add_argument('--transform_to_json', dest='to_json',
                        action='store_true', default=False,
                        help='Convert the passed value to a JSON string')

    parser.add_argument('--transform_to_json_pretty', dest='to_json_pretty',
                        action='store_true', default=False,
                        help='Convert the passed value to a pretty-printed '
                        'JSON string')

    parser.add_argument('--transform_from_json', dest='from_json',
                        action='store_true', default=False,
                        help='Convert the passed string, assumed to be JSON '
                        'to a dict.')

    parser.add_argument('--transform_from_json_to_das_record',
                        dest='from_json_to_das_record',
                        action='store_true', default=False,
                        help='Convert the passed string, assumed to be JSON '
                        'to a DASRecord.')

    parser.add_argument('--transform_to_das_record', dest='to_das_record',
                        default=None, help='Convert the passed value to a '
                        'DASRecord with single field whose name is the string '
                        'specified here.')

    ############################
    # Writers
    parser.add_argument('--write_file', dest='write_file', default=None,
                        help='File(s) to write to (\'-\' for stdout)')

    parser.add_argument('--write_logfile', dest='write_logfile', default=None,
                        help='Filename base to write to. A date string that '
                        'corresponds to the timestamped date of each record '
                        'Will be appended to filename, with one file per date.')

    parser.add_argument('--write_network', dest='write_network', default=None,
                        help='Network address(es) to write to.  NOTE: This has '
                        'been REPLACED by --write_udp and --write_tcp.')

    parser.add_argument('--write_tcp', dest='write_tcp', default=None,
                        help='TCP destination host/IP(s) and port(s) to write '
                        'to. Format destination:port[,...].  NOTE: This replaces '
                        'the old --write_network argument.')

    parser.add_argument('--write_udp', dest='write_udp', default=None,
                        help='UDP interface(s) and port(s) to write to. Format '
                        '[destination:]port[,...].  NOTE: This replaces the old '
                        '--write_network argument.')

    parser.add_argument('--write_serial', dest='write_serial', default=None,
                        help='Comma-separated serial port spec containing at '
                        'least port=[port], but also optionally baudrate, '
                        'timeout, max_bytes and/or other SerialReader '
                        'parameters.')

    parser.add_argument('--network_eol', dest='network_eol', default=None,
                        help='Optional EOL string to add to writen records.')

    parser.add_argument('--encoding', dest='encoding', default='utf-8',
                        help="Optional encoding of records.  Default is utf-8, "
                        "specify '' for raw/binary.  NOTE: This applies to ALL "
                        "readers/writers/transforms, as you need to have one "
                        "consistent encoding from start to finish.")

    parser.add_argument('--write_redis', dest='write_redis', default=None,
                        help='Redis pubsub channel[@host[:port]] to write to. '
                        'Defaults to localhost:6379.')

    parser.add_argument('--write_database', dest='write_database', default=None,
                        help='user@host:database to write to. Should be '
                        'accompanied by the --database_password flag.')

    parser.add_argument('--database_password', dest='database_password',
                        default=None, help='Password for database specified by '
                        '--write_database and/or --read_database.')

    parser.add_argument('--write_cached_data_server',
                        dest='write_cached_data_server', default=None,
                        help='Write to a CachedDataServer at the specified '
                        'host:port')

    parser.add_argument('--write_record_screen', dest='write_record_screen',
                        action='store_true', default=False,
                        help='Display the most current DASRecord field values '
                        'on the terminal.')

    ############################
    # Miscellaneous args
    parser.add_argument('--check_format', dest='check_format',
                        action='store_true', default=False, help='Check '
                        'reader/transform/writer format compatibility')

    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')

    parsed_args = parser.parse_args()

    ############################
    # Set up logging before we do any other argument parsing (so that we
    # can log problems with argument parsing).

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    log_level = LOG_LEVELS[min(parsed_args.verbosity, max(LOG_LEVELS))]
    logging.getLogger().setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(STDERR_FORMATTER)
    logging.root.handlers = [console_handler]

    ############################
    # If --config_file/--config_string present, create Listener from
    # config file/string. If not, manually parse and create from all
    # other arguments on command line.
    if parsed_args.config_file and parsed_args.config_string:
        parser.error('You may not specify both --config_file and --config_string')

    if parsed_args.config_file or parsed_args.config_string:
        # Ensure that no other flags have been specified.
        i = 1
        while i < len(sys.argv):
            if sys.argv[i] in ['-v', '--verbosity']:
                i += 1
            elif '--config_file'.find(sys.argv[i]) == 0:
                i += 2
            elif '--config_string'.find(sys.argv[i]) == 0:
                i += 2
            else:
                parser.error('When --config_file or --config_string are '
                             'specified, no other command line args except -v, '
                             'may be used: '
                             '{}'.format(sys.argv[i]))

        # Read config file or JSON string and instantiate.
        if parsed_args.config_file:
            listener = ListenerFromLoggerConfigFile(parsed_args.config_file)
        else:
            listener = ListenerFromLoggerConfigString(parsed_args.config_string)

    # If not --config, go parse all those crazy command line arguments manually
    else:
        ############################
        # Where we'll store our components
        readers = []
        transforms = []
        writers = []
        stderr_writers = []

        ############################
        # Parse args out. We do this in a rather non-standard way to use the
        # order of args on the command line to determine the order of our
        # transforms. Specifically: break command line up into sections that
        # end with the next '-'-prefixed argument (excluding the empty
        # argument '-' and arguments starting with a negative number),
        # and process those sections sequentially, adding
        # them to the 'args' namespace as we go.
        #
        # So
        #
        #    listen.py  -v 1 2 3 -w -x - -y -4 -1,1 -z
        #
        # will be processed in five chunks:
        #
        #    ['-v', '1', '2', '3']
        #    ['-w']
        #    ['-x', '-']
        #    ['-y', '-4', '-1,1']
        #    ['-z']
        #
        #
        # Functionally, it means that
        #
        #    --transform_a <params_a> --transform_b <params_b>
        #
        # will push transform_a into the transform list before transform_b,
        # (meaning it will be applied to records first), while
        #
        #    --transform_b <params_b> --transform_a <params_a>
        #
        # will do the opposite. It also means that repeating a transform on
        # the command line will apply it twice. Repetitions of readers or
        # writers will create multiple instances but, since readers and
        # writers are applied in parallel, ordering is irrelevant.

        arg_start = arg_end = 1   # start at beginning of args, minus script name;
        all_args = None           # initial namespace is empty

        # Loop while we have args left
        while arg_end <= len(sys.argv):

            arg_start = arg_end
            arg_end += 1

            # Get everything up to, but not including, the next arg beginning with '-'
            # that isn't a plain '-' or something numeric.
            while arg_end < len(sys.argv):
                next_arg = sys.argv[arg_end]
                if next_arg.find('-') == 0:
                    if next_arg != '-' and not re.match('-\d', next_arg):  # noqa: W605
                        break
                arg_end += 1

            # We have our next set of arguments - parse them
            arg_list = sys.argv[arg_start:arg_end]
            logging.debug('next set of command line arguments: %s', arg_list)

            # These are just the new values
            new_args = parser.parse_args(arg_list)

            # We also want to accumulate old arguments so that we have access
            # to flags that have been previously set.
            all_args = parser.parse_args(arg_list, all_args)

            logging.debug('namespace of all command-line args so far: %s', all_args)

            ##########################
            # Now go through new_args and see what they want us to do. Draw
            # on all_args for the previously-set options that a reader,
            # transform or writer might need.

            ##########################
            # Readers
            if new_args.file:
                for filename in new_args.file.split(','):
                    readers.append(TextFileReader(
                        file_spec=filename, tail=all_args.tail,
                        refresh_file_spec=all_args.refresh_file_spec))

            if new_args.network:
                encoding = parsed_args.encoding
                for addr in new_args.network.split(','):
                    readers.append(NetworkReader(network=addr, encoding=encoding))

            if new_args.tcp:
                eol = all_args.network_eol
                encoding = parsed_args.encoding
                for addr_str in new_args.tcp.split(','):
                    addr = addr_str.split(':')
                    if len(addr) > 2:
                        parser.error('Format error for --tcp argument. Format '
                                     'should be [source:]port,[,...]')
                    if len(addr) < 2:
                        addr.insert(0, '')
                    source = addr[0]
                    port = int(addr[1])
                    readers.append(TCPReader(source, port, eol=eol, encoding=encoding))

            if new_args.udp:
                encoding = parsed_args.encoding
                for addr_str in new_args.udp.split(','):
                    addr = addr_str.split(':')
                    if len(addr) > 2:
                        parser.error('Format error for --udp argument. Format '
                                     'should be [source:]port[,...]')
                    if len(addr) < 2:
                        addr.insert(0, '')
                    source = addr[0]
                    port = int(addr[1])
                    readers.append(UDPReader(source, port, encoding=encoding))

            if new_args.redis:
                for channel in new_args.redis.split(','):
                    readers.append(RedisReader(channel=channel))

            if new_args.logfile:
                for filebase in new_args.logfile.split(','):
                    readers.append(LogfileReader(
                        filebase=filebase, use_timestamps=all_args.logfile_use_timestamps,
                        time_format=all_args.time_format,
                        refresh_file_spec=all_args.refresh_file_spec))

            if new_args.cached_data_server:
                fields = new_args.cached_data_server
                server = None
                if fields.find('@') > 0:
                    fields, server = fields.split('@')
                subscription = {'fields': {f: {'seconds': 0} for f in fields.split(',')}}
                if server:
                    readers.append(CachedDataReader(subscription=subscription,
                                                    data_server=server))
                else:
                    readers.append(CachedDataReader(subscription=subscription))

            # For each comma-separated spec, parse out values for
            # user@host:database:data_id[:message_type]. We count on
            # --database_password having been specified somewhere.
            if new_args.database:
                password = all_args.database_password
                (user, host_db) = new_args.database.split('@')
                (host, database) = host_db.split(':', maxsplit=1)
                if ':' in database:
                    (database, fields) = database.split(':')
                else:
                    fields = None
                readers.append(DatabaseReader(fields=fields,
                                              database=database, host=host,
                                              user=user, password=password))

            # SerialReader is a little more complicated than other readers
            # because it can take so many parameters. Use the kwargs trick to
            # pass them all in.
            if new_args.serial:
                kwargs = {}
                for pair in new_args.serial.split(','):
                    (key, value) = pair.split('=')
                    kwargs[key] = value
                readers.append(SerialReader(**kwargs))

            ##########################
            # Transforms
            if new_args.slice:
                transforms.append(SliceTransform(new_args.slice,
                                                 all_args.slice_separator))
            if new_args.nmea:
                transforms.append(NMEATransform(new_args.nmea))
            if new_args.timestamp:
                transforms.append(TimestampTransform(time_format=all_args.time_format))
            if new_args.prefix:
                transforms.append(PrefixTransform(new_args.prefix))
            if new_args.extract:
                transforms.append(ExtractFieldTransform(new_args.extract))
            if new_args.regex_filter:
                transforms.append(RegexFilterTransform(new_args.regex_filter))
            if new_args.qc_filter:
                transforms.append(QCFilterTransform(new_args.qc_filter))
            if new_args.parse_nmea:
                transforms.append(
                    ParseNMEATransform(
                        message_path=all_args.parse_nmea_message_path,
                        sensor_path=all_args.parse_nmea_sensor_path,
                        sensor_model_path=all_args.parse_nmea_sensor_model_path,
                        time_format=all_args.time_format)
                )
            if new_args.parse:
                transforms.append(
                    ParseTransform(
                        definition_path=all_args.parse_definition_path,
                        return_json=all_args.parse_to_json,
                        return_das_record=all_args.parse_to_das_record)
                )
            if new_args.aggregate_xml:
                transforms.append(XMLAggregatorTransform(new_args.aggregate_xml))

            if new_args.max_min:
                transforms.append(MaxMinTransform())

            if new_args.count:
                transforms.append(CountTransform())

            if new_args.to_json:
                transforms.append(ToJSONTransform())

            if new_args.to_json_pretty:
                transforms.append(ToJSONTransform(pretty=True))

            if new_args.from_json:
                transforms.append(FromJSONTransform())

            if new_args.from_json_to_das_record:
                transforms.append(FromJSONTransform(das_record=True))

            if new_args.to_das_record:
                transforms.append(
                    ToDASRecordTransform(field_name=new_args.to_das_record))

            ##########################
            # Writers
            if new_args.write_file:
                encoding = parsed_args.encoding
                for filename in new_args.write_file.split(','):
                    if filename == '-':
                        filename = None
                    writers.append(FileWriter(filename=filename, encoding=encoding))

            if new_args.write_logfile:
                writers.append(LogfileWriter(filebase=new_args.write_logfile))

            if new_args.write_network:
                eol = all_args.network_eol
                encoding = parsed_args.encoding
                for addr in new_args.write_network.split(','):
                    writers.append(NetworkWriter(network=addr, eol=eol, encoding=encoding))

            if new_args.write_tcp:
                eol = all_args.network_eol
                encoding = parsed_args.encoding
                for addr_str in new_args.write_tcp.split(','):
                    addr = addr_str.split(':')
                    if len(addr) > 2:
                        parser.error('Format err for --write_tcp argument. Format '
                                     'should be [destination:]port[,...]')
                    if len(addr) < 2:
                        addr.insert(0, '')
                    dest = addr[0]
                    port = int(addr[1])
                    writers.append(TCPWriter(dest, port, eol=eol, encoding=encoding))

            if new_args.write_udp:
                eol = all_args.network_eol
                encoding = parsed_args.encoding
                for addr_str in new_args.write_udp.split(','):
                    addr = addr_str.split(':')
                    if len(addr) > 2:
                        parser.error('Format error for --write_udp argument. Format '
                                     'should be [destination:]port[,...]')
                    if len(addr) < 2:
                        addr.insert(0, '')
                    dest = addr[0]
                    port = int(addr[1])
                    writers.append(UDPWriter(dest, port, eol=eol, encoding=encoding))

            # SerialWriter is a little more complicated than other readers
            # because it can take so many parameters. Use the kwargs trick to
            # pass them all in.
            if new_args.write_serial:
                kwargs = {}
                for pair in new_args.write_serial.split(','):
                    (key, value) = pair.split('=')
                    kwargs[key] = value
                writers.append(SerialWriter(**kwargs))

            if new_args.write_redis:
                for channel in new_args.write_redis.split(','):
                    writers.append(RedisWriter(channel=channel))

            if new_args.write_record_screen:
                writers.append(RecordScreenWriter())

            if new_args.write_database:
                password = all_args.database_password
                # Parse out values for user@host:database. We count on
                # --database_password having been specified somewhere.
                (user, host_db) = new_args.write_database.split('@')
                (host, database) = host_db.split(':')
                writers.append(DatabaseWriter(database=database, host=host,
                                              user=user, password=password))

            if new_args.write_cached_data_server:
                data_server = new_args.write_cached_data_server
                writers.append(CachedDataWriter(data_server=data_server))

        ##########################
        # If we don't have any readers, read from stdin, if we don't have
        # any writers, write to stdout.
        if not readers:
            readers.append(TextFileReader())
        if not writers:
            writers.append(FileWriter())

        ##########################
        # Now that we've got our readers, transforms and writers defined,
        # create the Listener.
        listener = Listener(readers=readers, transforms=transforms, writers=writers,
                            stderr_writers=stderr_writers,
                            interval=all_args.interval,
                            check_format=all_args.check_format)

    ############################
    # Whichever way we created the listener, run it.
    listener.run()
