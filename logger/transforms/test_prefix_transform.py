#!/usr/bin/env python3

import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.prefix_transform import PrefixTransform  # noqa: E402


class TestPrefixTransform(unittest.TestCase):

    def test_default(self):
        transform = PrefixTransform('prefix')
        self.assertIsNone(transform.transform(None))
        self.assertEqual(transform.transform('foo'), 'prefix foo')

        transform = PrefixTransform('prefix', sep='\t')
        self.assertEqual(transform.transform('foo'), 'prefix\tfoo')


if __name__ == '__main__':
    unittest.main()
