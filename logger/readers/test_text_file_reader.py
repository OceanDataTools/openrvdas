#!/usr/bin/env python3

import logging
import sys
import tempfile
import threading
import time
import unittest
import warnings

sys.path.append('.')

from logger.readers.text_file_reader import TextFileReader
from logger.utils import formats

SAMPLE_DATA = {
  'f1' : ['f1 line 1',
          'f1 line 2',
          'f1 line 3'],
  'f2' : ['f2 line 1',
          'f2 line 2',
          'f2 line 3'],
  'f3' : ['f3 line 1',
          'f3 line 2',
          'f3 line 3']
  }

def create_file(filename, lines, interval=0, pre_sleep_interval=0):
  time.sleep(pre_sleep_interval)
  logging.info('creating file "%s"', filename)
  f = open(filename, 'w')
  for line in lines:
    time.sleep(interval)
    f.write(line + '\n')
    f.flush()
  f.close()

class TestTextFileReader(unittest.TestCase):
  ############################
  # To suppress resource warnings about unclosed files
  def setUp(self):
    warnings.simplefilter("ignore", ResourceWarning)

  ############################
  def test_all_files(self):
    with tempfile.TemporaryDirectory() as tmpdirname:
      logging.info('created temporary directory "%s"', tmpdirname)
      expected_lines = []
      for f in sorted(SAMPLE_DATA):
        create_file(tmpdirname + '/' + f, SAMPLE_DATA[f])
        expected_lines.extend(SAMPLE_DATA[f])

      reader = TextFileReader(tmpdirname + '/f*')
      for line in expected_lines:
        self.assertEqual(line, reader.read())
      self.assertEqual(None, reader.read())

  ############################
  def test_tail_false(self):
    # Don't specify 'tail' and expect there to be no data
    with tempfile.TemporaryDirectory() as tmpdirname:
      logging.info('created temporary directory "%s"', tmpdirname)
      expected_lines = []

      # Create a file slowly, one line at a time
      target = 'f1'
      tmpfilename = tmpdirname + '/' + target
      threading.Thread(target=create_file,
                       args=(tmpfilename, SAMPLE_DATA[target], 0.25)).start()

      time.sleep(0.05) # let the thread get started

      # Read, and wait for lines to come
      reader = TextFileReader(tmpfilename, tail=False)
      self.assertEqual(None, reader.read())

  ############################
  def test_tail_true(self):
    # Do the same thing as test_tail_false, but specify tail=True. We should
    # now get all the lines that are eventually written to the file.
    with tempfile.TemporaryDirectory() as tmpdirname:
      logging.info('created temporary directory "%s"', tmpdirname)
      expected_lines = []

      # Create a file slowly, one line at a time
      target = 'f1'
      tmpfilename = tmpdirname + '/' + target
      threading.Thread(target=create_file,
                       args=(tmpfilename, SAMPLE_DATA[target], 0.25)).start()

      time.sleep(0.05) # let the thread get started

      # Read, and wait for lines to come
      reader = TextFileReader(tmpfilename, tail=True)
      for line in SAMPLE_DATA[target]:
        self.assertEqual(line, reader.read())

  ############################
  def test_refresh_file_spec(self):
    # Delay creation of the file, but tell reader to keep checking for
    # new files.
    with tempfile.TemporaryDirectory() as tmpdirname:
      logging.info('created temporary directory "%s"', tmpdirname)
      expected_lines = []

      # Create a file slowly, one line at a time, and delay even
      # creating the file so that when our TextFileReader starts, its
      # file_spec matches nothing.
      target = 'f1'
      tmpfilename = tmpdirname + '/' + target
      threading.Thread(target=create_file,
                       args=(tmpfilename, SAMPLE_DATA[target],
                             0.25, 0.5)).start()
      
      time.sleep(0.05) # let the thread get started

      with self.assertLogs(logging.getLogger(), logging.WARNING):
        reader = TextFileReader(tmpfilename, refresh_file_spec=True)
      for line in SAMPLE_DATA[target]:
        self.assertEqual(line, reader.read())

  ############################
  # Check that reader output_formats work the way we expect
  def test_formats(self):
    reader = TextFileReader(file_spec=None)

    self.assertEqual(reader.output_format(), formats.Text)
    self.assertEqual(reader.output_format(formats.NMEA), formats.NMEA)
    self.assertEqual(reader.output_format(), formats.NMEA)
    
    with self.assertRaises(TypeError):
      reader.output_format('not a format')

if __name__ == '__main__':
    unittest.main()
