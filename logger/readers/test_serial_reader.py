#!/usr/bin/env python3

import logging
import serial
import sys
import tempfile
import time
import threading
import unittest
import warnings

sys.path.append('.')

from logger.readers.serial_reader import SerialReader
from logger.transforms.slice_transform import SliceTransform

from logger.utils import read_json
from logger.utils.simulate_serial import SimSerial

PORT = '%DIR%/tty_gyr1'

SAMPLE_CONFIG = """{
    "gyr1": {"port": "%DIR%/tty_gyr1",
             "logfile": "%DIR%/NBP1700_gyr1" 
            }
}
"""

SAMPLE_DATA = """2017-11-04:05:12:19.275337 $HEHDT,234.76,T*1b
2017-11-04:05:12:19.527360 $HEHDT,234.73,T*1e
2017-11-04:05:12:19.781738 $HEHDT,234.72,T*1f
2017-11-04:05:12:20.035450 $HEHDT,234.72,T*1f
2017-11-04:05:12:20.286551 $HEHDT,234.73,T*1e
2017-11-04:05:12:20.541843 $HEHDT,234.76,T*1b
2017-11-04:05:12:20.796684 $HEHDT,234.81,T*13
2017-11-04:05:12:21.047098 $HEHDT,234.92,T*11
2017-11-04:05:12:21.302371 $HEHDT,235.06,T*1d
2017-11-04:05:12:21.557630 $HEHDT,235.22,T*1b
2017-11-04:05:12:21.809445 $HEHDT,235.38,T*10
2017-11-04:05:12:22.062809 $HEHDT,235.53,T*1d
2017-11-04:05:12:22.312971 $HEHDT,235.66,T*1b"""

SAMPLE_MAX_BYTES_2 = ['$H',
                      'EH',
                      'DT',
                      ',2',
                      '34',
                      '.7',
                      '6,',
                      'T*',
                      '1b']

SAMPLE_TIMEOUT = [None,
                  '$HEHDT,234.76,T*1b',
                  None, None,
                  '$HEHDT,234.73,T*1e',
                  None, None,
                  '$HEHDT,234.72,T*1f',
                  None, None,
                  '$HEHDT,234.72,T*1f',
                  None, None]

################################################################################
class TestSerialReader(unittest.TestCase):

  ############################
  # Set up config file and sample logfile to feed simulated serial port
  def setUp(self):
    warnings.simplefilter("ignore", ResourceWarning)

    # Set up config file and logfile simulated serial port will read from
    self.tmpdir = tempfile.TemporaryDirectory()
    self.tmpdirname = self.tmpdir.name
    logging.info('created temporary directory "%s"', self.tmpdirname)

    self.config_filename = self.tmpdirname + '/gyr.config'
    self.logfile_filename = self.tmpdirname + '/NBP1700_gyr1-2017-11-04'

    with open(self.config_filename, 'w') as f:
      config_str = SAMPLE_CONFIG.replace('%DIR%', self.tmpdirname)
      f.write(config_str)
    with open(self.logfile_filename, 'w') as f:
      f.write(SAMPLE_DATA)

  ############################
  # When max_bytes is not specified, SerialReader should read port up
  # to a newline character.
  def test_readline(self):
    port = PORT.replace('%DIR%', self.tmpdirname)
    sim = SimSerial(port=port, source_file=self.logfile_filename,
                    use_timestamps=False)
    sim_thread = threading.Thread(target=sim.run)
    sim_thread.start()

    # Give it a moment to get started
    time.sleep(0.1)

    slice = SliceTransform('1:')  # we'll want to strip out timestamp
    
    # Then read from serial port
    s = SerialReader(port=port)
    for line in SAMPLE_DATA.split('\n'):
      data = slice.transform(line)
      record = s.read()
      logging.debug('data: %s, read: %s', data, record)
      self.assertEqual(data, record)

  ############################
  # When max_bytes specified, read up to that many bytes each time.
  def test_read_bytes(self):
    port = PORT.replace('%DIR%', self.tmpdirname)
    sim = SimSerial(port=port, source_file=self.logfile_filename,
                    use_timestamps=False)
    sim_thread = threading.Thread(target=sim.run)
    sim_thread.start()

    # Give it a moment to get started
    time.sleep(0.1)

    slice = SliceTransform('1:')  # we'll want to strip out timestamp
    
    # Then read from serial port
    s = SerialReader(port=port, max_bytes=2)
    for data in SAMPLE_MAX_BYTES_2:
      record = s.read()
      logging.debug('data: %s, read: %s', data, record)
      self.assertEqual(data, record)
  
  ############################
  # When timeout specified...
  def test_timeout(self):
    port = PORT.replace('%DIR%', self.tmpdirname)
    sim = SimSerial(port=port, source_file=self.logfile_filename)
    sim_thread = threading.Thread(target=sim.run)
    sim_thread.start()

    # Give it a moment to get started
    time.sleep(0.1)

    slice = SliceTransform('1:')  # we'll want to strip out timestamp
    
    # Then read from serial port
    s = SerialReader(port=port, timeout=0.1)
    for line in SAMPLE_TIMEOUT:
      record = s.read()
      logging.debug('data: %s, read: %s', line, record)
      self.assertEqual(line, record)

################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
  
  #unittest.main(warnings='ignore')
  unittest.main()
    
