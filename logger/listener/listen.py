#!/usr/bin/env python3
"""Instantiates and runs the Listener class. Try

  listen.py --help

for details.

Examples:

  logger/listener/listen.py \
    --logfile test/nmea/NBP1700/s330/raw/NBP1700_s330 \
    --interval 0.25 \
    --transform_slice 1: \
    --transform_timestamp \
    --transform_prefix s330 \
    --write_file -

(Reads lines from the Seapath300 sample logfiles every 0.25 seconds,
strips the old timestamps off, prepends a new one, then the prefix
's330', then writes the result to stdout.)

  logger/listener/listen.py \
    --config_file test/configs/simple_logger.json

(Instantiates logger from config file that says to read from the
project's LICENSE file, prepend a timestamp and the string "license:"
and writ to stdout every 0.2 seconds.)

The listen.py script is essentially a form of 'cat' on steroids,
reading records from files, serial or network ports, modifying what it
receives, then writing it back out to somewhere else.

For fun, you can even run listen.py as an Ouroboros script, feeding it on its
own output:

  echo x > tmp
  listen.py --file tmp --prefix p --write_file tmp --tail --interval 1 -v -v

"""
import argparse
import logging
import re
import sys
import time

sys.path.append('.')

from logger.readers.composed_reader import ComposedReader
from logger.readers.logfile_reader import LogfileReader
from logger.readers.network_reader import NetworkReader
from logger.readers.serial_reader import SerialReader
from logger.readers.text_file_reader import TextFileReader

from logger.transforms.prefix_transform import PrefixTransform
from logger.transforms.regex_filter_transform import RegexFilterTransform
from logger.transforms.qc_filter_transform import QCFilterTransform
from logger.transforms.slice_transform import SliceTransform
from logger.transforms.timestamp_transform import TimestampTransform
from logger.transforms.parse_nmea_transform import ParseNMEATransform

from logger.writers.composed_writer import ComposedWriter
from logger.writers.network_writer import NetworkWriter
from logger.writers.text_file_writer import TextFileWriter
from logger.writers.logfile_writer import LogfileWriter
from logger.writers.record_screen_writer import RecordScreenWriter

from logger.utils import read_json
from logger.listener.listener import Listener

################################################################################
class ListenerFromConfig(Listener):
  """Helper class for instantiating a Listener object from a Python dict."""
  ############################
  def __init__(self, config):
    """Create a Listener from a Python config dict."""
    kwargs = self._kwargs_from_config(config)
    super().__init__(**kwargs)

  ############################
  def _kwargs_from_config(self, config_json):
    """Parse a kwargs from a JSON string, making exceptions for keywords
    'readers', 'transforms', and 'writers' as internal class references."""
    kwargs = {}
    for key, value in config_json.items():

      # Declaration of readers, transforms and writers
      if key in ['readers', 'transforms', 'writers']:
        kwargs[key] = self._class_kwargs_from_config(value)

      # If value is a simple float/int/string/etc, just add to keywords
      elif type(value) in [float, bool, int, str]:
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
    class_const = globals().get(class_name, None)
    if not class_const:
      raise ValueError('No component class "{}" found: "{}"'.format(
        class_name, class_json))

    # Get the keyword args for the component
    kwarg_dict = class_json.get('kwargs', {})
    kwargs = self._kwargs_from_config(kwarg_dict)
    if not kwargs:
      logging.info('No kwargs found for component {}'.format(class_name))

    # Instantiate!
    logging.info('Instantiating {}({})'.format(class_name, kwargs))
    component = class_const(**kwargs)
    return component

################################################################################
class ListenerFromConfigFile(ListenerFromConfig):
  """Helper class for instantiating a Listener object from a JSON config."""
  ############################
  def __init__(self, config_file):
    """Create a Listener from a Python config file."""
    config = read_json.read_json(config_file)
    super().__init__(config)

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
                      help='Read Listener configuration from JSON file. If '
                      'specified, no other command line arguments (except '
                      '-v) are allowed.')

  ############################
  # Readers
  parser.add_argument('--network', dest='network', default=None,
                      help='Comma-separated network addresses to read from')

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

  parser.add_argument('--transform_qc_filter', dest='qc_filter',
                      default='', help='Pass nothing unless the fields in the '
                      'received DASRecord exceed comma-separated '
                      '<field_name>:<lower>:<upper> bounds.')

  parser.add_argument('--transform_parse_nmea', dest='parse_nmea',
                      action='store_true', default=False,
                      help='Convert tagged, timestamped NMEA records into '
                      'Python DASRecords.')

  ############################
  # Writers
  parser.add_argument('--write_file', dest='write_file', default=None,
                      help='File(s) to write to (empty for stdout)')

  parser.add_argument('--write_logfile', dest='write_logfile', default=None,
                      help='Filename base to write to. A date string that '
                      'corresponds to the timestamped date of each record '
                      'Will be appended to filename, with one file per date.')

  parser.add_argument('--write_network', dest='write_network', default=None,
                      help='Network address(es) to write to')

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

  ############################
  # Set up logging before we do any other argument parsing (so that we
  # can log problems with argument parsing.)
  parsed_args = parser.parse_args() 
  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  verbosity = min(parsed_args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[verbosity])

  ############################
  # If --config_file present, create Listener from config file. If
  # not, manually parse and create from all other arguments on command
  # line.
  if parsed_args.config_file:
    # Ensure that no other flags have been specified.
    i = 1
    while i < len(sys.argv):
      if sys.argv[i] in ['-v', '--verbosity']:
        i += 1
      elif sys.argv[i] == '--config_file':
        i += 2
      else:
        raise ValueError(
          'When --config is specified, no other command '
          'line arguments (except -v) may be used: {}'.format(sys.argv[i]))

    # Read config file and instantiate
    listener = ListenerFromConfigFile(parsed_args.config_file)

  # If not --config, go parse all those crazy command line arguments manually
  else:
    ############################
    # Where we'll store our components
    readers = []
    transforms = []
    writers = []

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
          if next_arg != '-' and not re.match('-\d', next_arg):
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
        for addr in new_args.network.split(','):
          readers.append(NetworkReader(network=addr))

      if new_args.logfile:
        for filebase in new_args.logfile.split(','):
          readers.append(LogfileReader(
            filebase=filebase, use_timestamps=all_args.logfile_use_timestamps,
            refresh_file_spec=all_args.refresh_file_spec))

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
      if new_args.timestamp:
        transforms.append(TimestampTransform())
      if new_args.prefix:
        transforms.append(PrefixTransform(new_args.prefix))
      if new_args.regex_filter:
        transforms.append(RegexFilterTransform(new_args.regex_filter))
      if new_args.qc_filter:
        transforms.append(QCFilterTransform(new_args.qc_filter))
      if new_args.parse_nmea:
        transforms.append(ParseNMEATransform())

      ##########################
      # Writers
      if new_args.write_file:
        for filename in new_args.write_file.split(','):
          if filename == '-':
            filename = None
          writers.append(TextFileWriter(filename=filename))
      if new_args.write_logfile:
        writers.append(LogfileWriter(filebase=new_args.write_logfile))
      if new_args.write_network:
        for addr in new_args.write_network.split(','):
          writers.append(NetworkWriter(network=addr))
      if new_args.write_record_screen:
        writers.append(RecordScreenWriter())

    ##########################
    # Now that we've got our readers, transforms and writers defined,
    # create the Listener.
    listener = Listener(readers=readers, transforms=transforms, writers=writers,
                        interval=all_args.interval,
                        check_format=all_args.check_format)

  ############################
  # Whichever way we created the listener, run it.
  listener.run()
