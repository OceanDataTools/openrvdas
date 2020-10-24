#!/usr/bin/env python3

import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.readers import reader  # noqa: E402
from logger.writers import writer  # noqa: E402


class TestWriter(unittest.TestCase):

    def test_can_accept(self):
        byte_w = writer.Writer(input_format=formats.Bytes)
        json_w = writer.Writer(input_format=formats.JSON)
        json_rec_r = reader.Reader(output_format=formats.JSON_Record)
        text_r = reader.Reader(output_format=formats.Text)
        unknown_r = reader.Reader(output_format=formats.Unknown)

        self.assertTrue(byte_w.can_accept(json_rec_r))
        self.assertTrue(json_w.can_accept(json_rec_r))

        self.assertFalse(json_w.can_accept(text_r))
        self.assertFalse(byte_w.can_accept(unknown_r))
        self.assertFalse(byte_w.can_accept(byte_w))  # no output_format()

    def test_not_implemented(self):
        byte_w = writer.Writer(input_format=formats.Bytes)
        with self.assertRaises(NotImplementedError):
            byte_w.write('this should fail')

    """
  def test_unknown(self):
    self.assertFalse(formats.Unknown.can_accept(formats.JSON_Record))
    self.assertFalse(formats.Python_Record.can_accept(formats.Unknown))

    self.assertEqual(formats.Unknown.common(formats.JSON_Record), None)
    self.assertEqual(formats.JSON_Record.common(formats.Unknown), None)
  """


if __name__ == '__main__':
    unittest.main()
