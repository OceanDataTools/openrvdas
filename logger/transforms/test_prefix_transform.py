#!/usr/bin/env python3

import logging
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

    def test_map(self):
        transform = PrefixTransform({'p1': 'prefix1',
                                     'p2':'prefix2'},
                                    quiet=True)
        self.assertIsNone(transform.transform(None))
        self.assertEqual(transform.transform('foop1'), 'prefix1 foop1')
        self.assertEqual(transform.transform('foop2'), 'prefix2 foop2')
        self.assertEqual(transform.transform('foo'), None)

        transform = PrefixTransform({'p1': 'prefix1',
                                     'p2':'prefix2',
                                     '':'prefix3'},
                                    quiet=True)
        self.assertEqual(transform.transform('foop1'), 'prefix1 foop1')
        self.assertEqual(transform.transform('foop2'), 'prefix2 foop2')
        self.assertEqual(transform.transform('foo'), 'prefix3 foo')

        transform = PrefixTransform({'p1': 'prefix1',
                                     'p2':'prefix2'})
        with self.assertLogs(logging.getLogger(), logging.WARNING):
            transform.transform('foo')


if __name__ == '__main__':
    unittest.main()
