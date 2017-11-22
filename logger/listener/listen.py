#!/usr/bin/env python3
"""Contains the Listener class and a __main__ that instantiates the
class and can be run as a standalone script (try 'listen.py --help'
for details).

NOTE: for fun, run listen.py as an Ouroboros script, feeding it on its
own output:

   echo x > tmp
   listen.py --file tmp --prefix p --write_file tmp --tail --interval 1 -v -v

"""
import argparse
import logging
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

################################################################################
class Listener:
  """Listener is a simple, yet relatively self-contained class that
  takes a list of one or more Readers, a list of zero or more
  Transforms, and a list of zero or more Writers. It calls the Readers
  (in parallel) to acquire records, passes those records through the
  Transforms (in series), and sends the resulting records to the Writers
  (in parallel).

  """
  ############################
  def __init__(self, readers, transforms=[], writers=[],
               interval=0, check_format=False):
    """
    listener = Listener(readers, transforms=[], writers=[],
                        interval=0, check_format=False)

    readers        A single Reader or a list of Readers.

    transforms     A single Transform or a list of zero or more Transforms

    writers        A single Writer or a list of zero or more Writers

    interval       How long to sleep before reading sequential records

    check_format   If True, attempt to check that Reader/Transform/Writer
                   formats are compatible, and throw a ValueError if they
                   are not. If check_format is False (the default) the
                   output_format() of the whole reader will be
                   formats.Unknown.
    Sample use:

    listener = Listener(readers=[NetworkReader(':6221'),
                                 NetworkReader(':6223')],
                        transforms=[TimestampTransform()],
                        writers=[TextFileWriter('/logs/network_recs'),
                                 TextFileWriter(None)],
                        interval=0.2)
    listener.run()

    Calling listener.quit() from another thread will cause the run() loop
    to exit.
    """
    self.reader = ComposedReader(readers=readers, check_format=check_format)
    self.writer = ComposedWriter(transforms=transforms, writers=writers,
                                 check_format=check_format)
    self.interval = interval
    self.last_read = 0
    
    self.quit_signalled = False

  ############################
  def quit(self):
    """
    Signal 'quit' to all the readers.
    """
    self.quit_signalled = True
    logging.debug('Listener.quit() called')
    
  ############################
  def run(self):
    """
    Read/transform/write until either quit() is called in a separate
    thread, or ComposedReader returns None, indicating that all its
    component readers have returned EOF.
    """
    record = ''
    while not self.quit_signalled and record is not None:
      record = self.reader.read()
      self.last_read = time.time()
      
      logging.debug('ComposedReader read: "%s"', record)
      if record:
        self.writer.write(record)

      if self.interval:
        time_to_sleep = self.interval - (time.time() - self.last_read)
        time.sleep(max(time_to_sleep, 0))

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
  # can log problems with argument parsing. 
  args_just_for_logging = parser.parse_args() 
  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  verbosity = min(args_just_for_logging.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[verbosity])

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
  # argument '-'), and process those sections sequentially, adding
  # them to the 'args' namespace as we go.
  #
  # So
  #
  #    listen.py  -v 1 2 3 -w -x - -y 4 5 -z
  #
  # will be processed in five chunks:
  #
  #    ['-v', '1', '2', '3']
  #    ['-w']
  #    ['-x', '-']
  #    ['-y', '4', '5']
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
    while arg_end < len(sys.argv):
      next_arg = sys.argv[arg_end]
      if next_arg.find('-') == 0 and next_arg != '-':
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
    # Now go through new args and see what they want us to do

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
      transforms.append(SliceTransform(args.slice, new_args.slice_separator))
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

  ############################
  # Create and run listener
  listener = Listener(readers, transforms, writers,
                      interval=all_args.interval,
                      check_format=all_args.check_format)
  listener.run()
