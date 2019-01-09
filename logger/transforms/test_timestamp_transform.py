#!/usr/bin/env python3

import sys
import unittest

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils import timestamp
from logger.transforms.timestamp_transform import TimestampTransform

class TestTimestampTransform(unittest.TestCase):

  def test_default(self):
    transform = TimestampTransform()

    self.assertIsNone(transform.transform(None))

    result = transform.transform('blah')
    time_str = result.split()[0]
    then = timestamp.timestamp(time_str=time_str)
    now = timestamp.timestamp()

    self.assertAlmostEqual(then, now, places=1)
    self.assertEqual(result.split()[1], 'blah')

  # Try handing a custom timestamp format (in this case, a date).  It
  # bears mentioning that this test will fail if run exactly at
  # midnight...
  def test_custom(self):
    transform = TimestampTransform(time_format=timestamp.DATE_FORMAT)

    self.assertIsNone(transform.transform(None))

    result = transform.transform('blah')
    today = timestamp.date_str()
    self.assertEqual(result.split()[0], today)
    self.assertEqual(result.split()[1], 'blah')

if __name__ == '__main__':
  unittest.main()
