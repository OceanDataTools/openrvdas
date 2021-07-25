#!/usr/bin/env python3

import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.transform import Transform  # noqa: E402
from logger.utils import formats  # noqa: E402


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
