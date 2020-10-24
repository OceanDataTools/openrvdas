#!/usr/bin/env python3

import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402


class TestFormat(unittest.TestCase):

    def test_can_accept(self):
        self.assertTrue(formats.Bytes.can_accept(formats.JSON_Record))
        self.assertFalse(formats.JSON.can_accept(formats.Bytes))
        self.assertTrue(formats.JSON.can_accept(formats.JSON_Record))
        self.assertTrue(formats.JSON_Record.can_accept(formats.JSON_Record))
        self.assertFalse(formats.JSON_Record.can_accept(formats.JSON))

    def test_common(self):
        self.assertEqual(formats.Python_Record.common(formats.JSON_Record),
                         formats.Bytes)
        self.assertEqual(formats.Python_Record.common(formats.Python),
                         formats.Python)
        self.assertEqual(formats.JSON_Record.common(formats.JSON_Record),
                         formats.JSON_Record)

    def test_unknown(self):
        self.assertFalse(formats.Unknown.can_accept(formats.JSON_Record))
        self.assertFalse(formats.Python_Record.can_accept(formats.Unknown))

        self.assertEqual(formats.Unknown.common(formats.JSON_Record), None)
        self.assertEqual(formats.JSON_Record.common(formats.Unknown), None)

    def test_is_format(self):
        self.assertTrue(formats.is_format(formats.Unknown))
        self.assertTrue(formats.is_format(formats.Bytes))
        self.assertTrue(formats.is_format(formats.JSON_Record))

        self.assertFalse(formats.is_format(formats.is_format))
        self.assertFalse(formats.is_format('a string'))
        self.assertFalse(formats.is_format(None))
        self.assertFalse(formats.is_format(self))


if __name__ == '__main__':
    unittest.main()
