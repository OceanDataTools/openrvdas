#!/usr/bin/env python3

import sys
import unittest

sys.path.append('.')

from logger.transforms.regex_filter_transform import RegexFilterTransform

class TestRegexFilterTransform(unittest.TestCase):

  def test_default(self):
    transform = RegexFilterTransform(pattern='^foo')
    self.assertIsNone(transform.transform(None))
    self.assertIsNone(transform.transform('not foo'))
    self.assertEqual(transform.transform('foo bar'), 'foo bar')

    transform = RegexFilterTransform(pattern='^foo', negate=True)
    self.assertEqual(transform.transform('not foo'), 'not foo')
    self.assertIsNone(transform.transform('foo bar'), 'foo bar')

    transform = RegexFilterTransform(pattern='^\dfoo')
    self.assertIsNone(transform.transform(None))
    self.assertIsNone(transform.transform('not foo'))
    self.assertEqual(transform.transform('9foo bar'), '9foo bar')

    transform = RegexFilterTransform(pattern='^\dfoo', negate=True)
    self.assertEqual(transform.transform('not foo'), 'not foo')
    self.assertIsNone(transform.transform('6foo bar'), 'foo bar')
    
    #transform = RegexFilterTransform('RegexFilter', sep='\t')
    #self.assertEqual(transform.transform('foo'), 'prefix\tfoo')

if __name__ == '__main__':
  unittest.main()
