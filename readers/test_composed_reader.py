#!/usr/bin/env python3

import logging
import sys
import tempfile
import threading
import time
import unittest
import warnings

sys.path.append('.')

from readers.text_file_reader import TextFileReader
from readers.composed_reader import ComposedReader
from readers.reader import Reader
from transforms.prefix_transform import PrefixTransform
from utils import formats

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

class TestComposedReader(unittest.TestCase):

  ############################
  # To suppress resource warnings about unclosed files
  def setUp(self):
    warnings.simplefilter("ignore", ResourceWarning)

    self.tmpdir = tempfile.TemporaryDirectory()
    self.tmpdirname = self.tmpdir.name
    logging.info('created temporary directory "%s"', self.tmpdirname)
      
    self.tmpfilenames = []
    for f in sorted(SAMPLE_DATA):
      logging.debug('Creating sample file %s', f)
      tmpfilename = self.tmpdirname + '/' + f
      self.tmpfilenames.append(tmpfilename)
      create_file(tmpfilename, SAMPLE_DATA[f])
    
  ############################
  def test_lock_setup(self):
    readers = []
    for tmpfilename in self.tmpfilenames:
      readers.append(TextFileReader(tmpfilename, interval=0.2))

    prefix_1 = PrefixTransform('prefix_1')
    prefix_2 = PrefixTransform('prefix_2')

    # This should be okay
    reader = ComposedReader(readers, [prefix_1, prefix_2])
    self.assertEqual(reader.transform_locks, None)

    # This should be okay
    reader = ComposedReader(readers, [prefix_1, prefix_2],
                            thread_lock_transforms=True)
    self.assertEqual(len(reader.transform_locks), 2)

    # This should not be okay
    with self.assertRaises(ValueError):
      reader = ComposedReader(readers, [prefix_1, prefix_2],
                            thread_lock_transforms=[True])
    
  ############################
  def test_check_format(self):

    # This should be okay
    ComposedReader([TextFileReader(self.tmpfilenames[0]),
                    TextFileReader(self.tmpfilenames[1])],
                   check_format=True)

    # This should not be - no common reader format
    with self.assertRaises(ValueError):
      ComposedReader([TextFileReader(self.tmpfilenames[0]), Reader()],
                     check_format=True)
    
  ############################
  def test_all_files(self):
    # Use TextFileReader's 'interval' flag to make sure we interleave
    # reads the way we expect. Also make sure transforms get applied
    # in proper order.

    readers = []
    for tmpfilename in self.tmpfilenames:
      readers.append(TextFileReader(tmpfilename, interval=0.2))

    prefix_1 = PrefixTransform('prefix_1')
    prefix_2 = PrefixTransform('prefix_2')

    # We don't really need to lock these transforms, but just
    # exercising that bit of code
    reader = ComposedReader(readers, [prefix_1, prefix_2],
                            thread_lock_transforms=[True, False])

    # Clunkly quick way of slicing lines
    i = 0
    expected_lines = []
    while True:
      next_lines = []
      for f in sorted(SAMPLE_DATA):
        if i < len(SAMPLE_DATA[f]):
          line = 'prefix_2 prefix_1 ' + SAMPLE_DATA[f][i]
          next_lines.append(line)
      if next_lines:
        expected_lines.append(next_lines)
        i += 1
      else:
        break
    logging.debug('Expected lines %s', expected_lines)
      
    # Next line from each of the files can come in arbitrary order,
    # but within the file, lines should arrive in order, and we
    # should receive first line from each file before we receive
    # next line from any of them.
    while expected_lines:
      next_lines = expected_lines.pop(0)
      while next_lines:
        record = reader.read()
        logging.debug('read: %s; expected one of: %s', record, next_lines)
        self.assertTrue(record in next_lines)
        if record in next_lines:
          next_lines.remove(record)
    self.assertEqual(None, reader.read())

if __name__ == '__main__':
  #logging.getLogger().setLevel(logging.DEBUG)
  unittest.main(warnings='ignore')
    
