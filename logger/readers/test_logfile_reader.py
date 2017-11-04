#!/usr/bin/env python3

import logging
import sys
import tempfile
import threading
import time
import unittest
import warnings

sys.path.append('.')

from logger.readers.logfile_reader import LogfileReader
from logger.utils import formats

SAMPLE_DATA = """2017-11-04:05:12:19.441672 3.5kHz,5360.54,1,,,,1500,-39.580717,-37.461886
2017-11-04:05:12:19.694789 3.5kHz,4569.66,1,,,,1500,-39.581014,-37.462332
2017-11-04:05:12:19.950082 3.5kHz,5123.88,1,,,,1500,-39.581264,-37.462718
2017-11-04:05:12:20.205345 3.5kHz,5140.06,0,,,,1500,-39.581545,-37.463151
2017-11-04:05:12:20.460595 3.5kHz,5131.30,1,,,,1500,-39.581835,-37.463586
2017-11-04:05:12:20.715024 3.5kHz,5170.92,1,,,,1500,-39.582138,-37.464015
2017-11-04:05:12:20.965842 3.5kHz,5137.89,0,,,,1500,-39.582438,-37.464450
2017-11-04:05:12:21.218870 3.5kHz,5139.14,0,,,,1500,-39.582731,-37.464887
2017-11-04:05:12:21.470677 3.5kHz,5142.55,0,,,,1500,-39.582984,-37.465285
2017-11-04:05:12:21.726024 3.5kHz,4505.91,1,,,,1500,-39.583272,-37.465733
2017-11-04:05:12:21.981359 3.5kHz,5146.29,0,,,,1500,-39.583558,-37.466183
2017-11-04:05:12:22.232898 3.5kHz,5146.45,0,,,,1500,-39.583854,-37.466634
2017-11-04:05:12:22.486203 3.5kHz,4517.82,0,,,,1500,-39.584130,-37.467078"""

def create_file(filename, lines, interval=0, pre_sleep_interval=0):
  time.sleep(pre_sleep_interval)
  logging.info('creating file "%s"', filename)
  f = open(filename, 'w')
  for line in lines:
    time.sleep(interval)
    f.write(line + '\n')
    f.flush()
  f.close()

class TestLogfileReader(unittest.TestCase):
  ############################
  # To suppress resource warnings about unclosed files
  def setUp(self):
    warnings.simplefilter("ignore", ResourceWarning)

  ############################
  def test_basic(self):
    with tempfile.TemporaryDirectory() as tmpdirname:
      logging.info('created temporary directory "%s"', tmpdirname)
      tmpfilename = tmpdirname + '/mylog-2017-02-02'
      sample_lines = SAMPLE_DATA.split('\n')
      create_file(tmpfilename, sample_lines)

      reader = LogfileReader(tmpfilename)
      for line in sample_lines:
        self.assertEqual(line, reader.read())
      self.assertEqual(None, reader.read())

  ############################
  def test_use_timestamp(self):
    with tempfile.TemporaryDirectory() as tmpdirname:
      logging.info('created temporary directory "%s"', tmpdirname)
      tmpfilename = tmpdirname + '/mylog-2017-02-02'
      sample_lines = SAMPLE_DATA.split('\n')
      create_file(tmpfilename, sample_lines)

      reader = LogfileReader(tmpfilename, use_timestamps=True)
      for line in sample_lines:
        self.assertEqual(line, reader.read())
      self.assertEqual(None, reader.read())

  ############################
  def test_use_timestamps(self):
    with tempfile.TemporaryDirectory() as tmpdirname:
      logging.info('created temporary directory "%s"', tmpdirname)
      tmpfilename = tmpdirname + '/mylog-2017-02-02'
      sample_lines = SAMPLE_DATA.split('\n')
      create_file(tmpfilename, sample_lines)

      # Logs timestamps were created artificially with ~0.25 intervals
      interval = 0.25
      reader = LogfileReader(tmpfilename, use_timestamps=True)
      then = 0
      for line in sample_lines:
        result = reader.read()
        self.assertEqual(line, result)
        now = time.time()
        if then:
          self.assertAlmostEqual(now-then, interval, places=1)
        then = now
        
      self.assertEqual(None, reader.read())
  
  ############################
  def test_interval(self):
    with tempfile.TemporaryDirectory() as tmpdirname:
      logging.info('created temporary directory "%s"', tmpdirname)
      tmpfilename = tmpdirname + '/mylog-2017-02-02'
      sample_lines = SAMPLE_DATA.split('\n')
      create_file(tmpfilename, sample_lines)

      interval = 0.2
      reader = LogfileReader(tmpfilename, interval=interval)
      then = 0
      for line in sample_lines:
        self.assertEqual(line, reader.read())
        now = time.time()
        if then:
          self.assertAlmostEqual(now-then, interval, places=1)
        then = now
        
      self.assertEqual(None, reader.read())

  ############################
  def test_tail_false(self):
    # Don't specify 'tail' and expect there to be no data
    with tempfile.TemporaryDirectory() as tmpdirname:
      logging.info('created temporary directory "%s"', tmpdirname)
      expected_lines = []

      # Create a file slowly, one line at a time
      target = 'mylogfile'
      tmpfilename = tmpdirname + '/' + target
      sample_lines = SAMPLE_DATA.split('\n')
      threading.Thread(target=create_file,
                       args=(tmpfilename, sample_lines, 0.25)).start()

      time.sleep(0.05) # let the thread get started

      # Read, and wait for lines to come
      reader = LogfileReader(tmpfilename, tail=False)
      self.assertEqual(None, reader.read())

  ############################
  def test_tail_true(self):
    # Do the same thing as test_tail_false, but specify tail=True. We should
    # now get all the lines that are eventually written to the file.
    with tempfile.TemporaryDirectory() as tmpdirname:
      logging.info('created temporary directory "%s"', tmpdirname)
      expected_lines = []

      # Create a file slowly, one line at a time
      target = 'mylogfile'
      tmpfilename = tmpdirname + '/' + target
      sample_lines = SAMPLE_DATA.split('\n')
      threading.Thread(target=create_file,
                       args=(tmpfilename, sample_lines, 0.25)).start()

      time.sleep(0.05) # let the thread get started

      # Read, and wait for lines to come
      reader = LogfileReader(tmpfilename, tail=True)
      for line in sample_lines:
        self.assertEqual(line, reader.read())

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
  
  unittest.main(warnings='ignore')
