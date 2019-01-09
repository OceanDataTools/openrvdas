#!/usr/bin/env python3
import logging
import subprocess
import sys
import threading
import time

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.readers.logfile_reader import LogfileReader
from logger.transforms.slice_transform import SliceTransform
from logger.writers.text_file_writer import TextFileWriter

from logger.utils.read_config import read_config

################################################################################
class SimSerial:
  """Create a virtual serial port and feed stored logfile data to it."""
  ############################
  def __init__(self, port, source_file, use_timestamps=True,
               baudrate=9600, bytesize=8, parity='N', stopbits=1,
               timeout=None, xonxoff=False, rtscts=False, write_timeout=None,
               dsrdtr=False, inter_byte_timeout=None, exclusive=None):
    """Takes source file, whether to deliver data at rate indicated by
    timestamps, and the standard parameters that a serial port takes."""
    self.source_file = source_file
    self.use_timestamps = use_timestamps

    # We'll create two virtual ports: 'port' and 'port_in'; we will write
    # to port_in and read the values back out from port
    self.read_port = port
    self.write_port = port + '_in'

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

    # Finally, check that our needed 'socat' actually exists
    if not subprocess.run(['which', 'socat'], stdout=subprocess.PIPE).stdout:
      raise NameError('Executable "socat" not found on path. Please refer '
                      'to installation guide to install socat.')

  ############################
  def _run_socat(self):
    """Internal: run the actual command."""
    verbose = '-d'
    write_port_params =   'pty,link=%s,raw,echo=0' % self.write_port
    read_port_params = 'pty,link=%s,raw,echo=0' % self.read_port

    cmd = ['/usr/bin/env',
           'socat',
           verbose,
           #verbose,   # repeating makes it more verbose
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
    """Create the virtual port with socat and start feeding it records from
    the designated logfile. If loop==True, loop when reaching end of input."""
    self.socat_thread = threading.Thread(target=self._run_socat)
    self.socat_thread.start()
    time.sleep(0.2)

    self.reader = LogfileReader(filebase=self.source_file,
                                use_timestamps=self.use_timestamps)
    self.strip = SliceTransform('1:') # strip off the first field)
    self.writer = TextFileWriter(self.write_port, truncate=True)

    while not self.quit:
      try:
        record = self.reader.read() # get the next record
        logging.debug('SimSerial got: %s', record)

        # End of input? If loop==True, re-open the logfile from the start
        if record is None:
          if not loop:
            break
          self.reader = LogfileReader(filebase=self.source_file,
                                      use_timestamps=self.use_timestamps)

        record = self.strip.transform(record)  # strip the timestamp
        if record:
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

  parser.add_argument('--logfile', dest='logfile',
                      help='Log file to read from.')

  parser.add_argument('--loop', dest='loop', action='store_true',
                      help='If True, loop when reaching end of sample data')

  parser.add_argument('--port', dest='port', help='Virtual serial port to open')
  parser.add_argument('--baud', dest='baud', type=int,
                      help='Baud rate for port.')

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
    for inst in configs:
      config = configs[inst]
      sim = SimSerial(port=config['port'], source_file=config['logfile'])
      sim_thread = threading.Thread(target=sim.run, kwargs={'loop': args.loop})
      sim_thread.start()
      thread_list.append(sim_thread)

    logging.warning('Running simulated ports for %s', ', '.join(configs.keys()))
    for thread in thread_list:
      thread.join()

  # If no config file, just a simple, single serial port
  elif args.logfile and args.port:
    sim_serial = SimSerial(port=args.port, baudrate=args.baud,
                           source_file=args.logfile)
    sim_serial.run(args.loop)

  # Otherwise, we don't have enough information to run
  else:
    parser.error('Either --config or both --logfile and --port must '
                 'be specified')
