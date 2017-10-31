#!/usr/bin/env python3

import logging
import sys
import tempfile
import threading
import time
import unittest

sys.path.append('.')

from readers.text_file_reader import TextFileReader
from writers.text_file_writer import TextFileWriter
from utils import formats

SAMPLE_DATA = ['f1 line 1',
               'f1 line 2',
               'f1 line 3']

def create_file(filename, lines, interval=0, pre_sleep_interval=0):
  time.sleep(pre_sleep_interval)
  logging.info('creating file "%s"', filename)
  f = open(filename, 'w')
  for line in lines:
    time.sleep(interval)
    f.write(line + '\n')
    f.flush()
  f.close()

class TestTextFileWriter(unittest.TestCase):

  ############################
  def test_write(self):
    with tempfile.TemporaryDirectory() as tmpdirname:
      writer = TextFileWriter(tmpdirname + '/f')
      f = open(tmpdirname + '/f')
      for line in SAMPLE_DATA:
        writer.write(line)
        self.assertEqual(line, f.readline().strip())

  ############################
  def test_compatible(self):
    # Don't specify 'tail' and expect there to be no data
    with tempfile.TemporaryDirectory() as tmpdirname:
      writer = TextFileWriter(tmpdirname + '/f')
      reader = TextFileReader(tmpdirname + '/f')
      self.assertTrue(writer.can_accept(reader))

  ############################
  # Check that writer input_formats work the way we expect
  def test_formats(self):
    writer = TextFileWriter(filename=None)

    self.assertEqual(writer.input_format(), formats.Text)
    self.assertEqual(writer.input_format(formats.NMEA), formats.NMEA)
    self.assertEqual(writer.input_format(), formats.NMEA)
    
    with self.assertRaises(TypeError):
      writer.input_format('not a format')

if __name__ == '__main__':
    unittest.main()
