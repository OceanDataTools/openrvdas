#!/usr/bin/env python3

import logging
import sys
import tempfile
import threading
import time
import unittest

sys.path.append('.')

from logger.transforms.transform import Transform
from logger.readers.text_file_reader import TextFileReader
from logger.writers.text_file_writer import TextFileWriter

from logger.utils import formats

class TestTransform(unittest.TestCase):

  ############################
  # Check that transform input/output_formats work the way we expect
  def test_formats(self):
    transform = Transform(input_format=formats.Text,
                          output_format=formats.Text)

    self.assertEqual(transform.input_format(), formats.Text)
    self.assertEqual(transform.input_format(formats.NMEA), formats.NMEA)
    self.assertEqual(transform.input_format(), formats.NMEA)

    with self.assertRaises(TypeError):
      transform.input_format('not a format')

    self.assertEqual(transform.output_format(), formats.Text)
    self.assertEqual(transform.output_format(formats.NMEA), formats.NMEA)
    self.assertEqual(transform.output_format(), formats.NMEA)

    with self.assertRaises(TypeError):
      transform.output_format('not a format')

if __name__ == '__main__':
    unittest.main()
