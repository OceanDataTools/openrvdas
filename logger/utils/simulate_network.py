#!/usr/bin/env python3
"""Read stored logger data and serve at realistic intervals over network ports.

Run with, e.g.

    logger/utils/simulate_network.py \
         --config test/nmea/SKQ201822S/network_sim_SKQ201822S.yaml \
         --loop

and you should be able to listen on the various ports that Sikuliaq
instruments post data to:

    logger/listener/listen.py --network :53131 --write_file -

for wind_mast_stbd (see test/sikuliaq/skq_ports.txt for a table of the
instrument to port mappings active during cruise SKQ201822.
"""
import logging
import subprocess
import sys
import threading
import time

sys.path.append('.')

from logger.readers.logfile_reader import LogfileReader
from logger.transforms.slice_transform import SliceTransform
from logger.transforms.timestamp_transform import TimestampTransform
from logger.transforms.prefix_transform import PrefixTransform
from logger.writers.network_writer import NetworkWriter

from logger.utils.read_config import read_config

################################################################################
class SimNetwork:
  """Open a network port and feed stored logfile data to it."""
  ############################
  def __init__(self, network, filebase, instrument):
    """Open a network port and feed stored logfile data to it.

    network port -  E.g.  my_host:80 for TCP or :54322 for UDP

    filebase - Prefix string to be matched (with a following "*") to fine
               files to be used. e.g. /tmp/log/NBP1406/knud/raw/NBP1406_knud

    instrument - Instrument name prefix to add before sendind out on wire
    """
    self.filebase = filebase
    self.reader = LogfileReader(filebase=filebase, use_timestamps=True)
    self.slice_n = SliceTransform(fields='1:') # grab 2nd and subsequent fields
    self.timestamp = TimestampTransform()
    self.prefix = PrefixTransform(instrument)
    self.writer = NetworkWriter(network=network)
    self.instrument = instrument
    self.first_time = True
    self.quit_flag = False
    
  ############################
  def run(self, loop=False):
    """Start reading and writing data. If loop==True, loop when reaching
    end of input.
    """
    logging.info('Starting %s', self.instrument)
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
          logging.info('Looping instrument %s', self.instrument)
          self.reader = LogfileReader(filebase=self.filebase,
                                      use_timestamps=True)
          continue

        # Strip off timestamp and tack on a new one
        record =  self.slice_n.transform(record)
        record = self.timestamp.transform(record)

        # Add instrument name back on, and write to specified network
        record = self.prefix.transform(record)
        self.writer.write(record)
        self.first_time = False

    except (OSError, KeyboardInterrupt):
      self.quit_flag = True

    logging.info('Finished %s', self.instrument)

################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()

  parser.add_argument('--config', dest='config', default=None,
                      help='Config file of JSON specs for port-file mappings.')

  parser.add_argument('--network', dest='network', default=None,
                      help='Network to write to. E.g. localhost:6224 for '
                      'TCP or :6224 for UDP.')

  parser.add_argument('--filebase', dest='filebase', default=None,
                      help='Base string of log file to be read from (with '
                      'a following "*" for match). E.g. '
                      '/tmp/log/NBP1406/knud/raw/NBP1406_knud')
  
  parser.add_argument('--instrument', dest='instrument', help='Prefix to add, '
                      'if file *doesn\'t* have instrument prefix')

  parser.add_argument('--loop', dest='loop', action='store_true',
                      help='If True, loop when reaching end of sample data')

  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  # Okay - get to work here
  if args.config:
    configs = read_config(args.config)
    logging.info('Read configs: %s', configs)
    thread_list = []
    writer_list = []
    for instrument, config in configs.items():
      network = config['network']
      filebase = config['filebase']
      writer = SimNetwork(network=network, filebase=filebase,
                          instrument=instrument)
      writer_thread = threading.Thread(target=writer.run,
                                       kwargs={'loop': args.loop})
      writer_thread.start()
      thread_list.append(writer_thread)
      writer_list.append('%s %s, %s' % (instrument, network, filebase))

    logging.warning('Running simulated ports for:\n%s', '\n'.join(writer_list))

    # Wait for all the threads to end
    for thread in thread_list:
      thread.join()

  # If no config file, just a simple, single network writer
  elif args.network and args.filebase:
    sim_network = SimNetwork(network=args.network, filebase=args.filebase,
                             instrument=args.instrument)
    sim_network.run(args.loop)

  # Otherwise, we don't have enough information to run
  else:
    parser.error('Either --config or --network, --filebase and --instrument '
                 'must be specified')
