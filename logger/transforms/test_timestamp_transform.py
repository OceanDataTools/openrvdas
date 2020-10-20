#!/usr/bin/env python3

import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import timestamp  # noqa: E402
from logger.transforms.timestamp_transform import TimestampTransform  # noqa: E402


class TestTimestampTransform(unittest.TestCase):

    ############################
    def test_default(self):
        transform = TimestampTransform()

        self.assertIsNone(transform.transform(None))

        result = transform.transform('blah')
        time_str = result.split()[0]
        then = timestamp.timestamp(time_str=time_str)
        now = timestamp.timestamp()

        self.assertAlmostEqual(then, now, places=1)
        self.assertEqual(result.split()[1], 'blah')

    ############################
    def test_list(self):
        transform = TimestampTransform()

        self.assertIsNone(transform.transform(None))

        record = ['foo', 'bar', 'baz']
        result = transform.transform(record)
        timestamps = [r.split()[0] for r in result]
        self.assertEqual(timestamps[0], timestamps[1])
        self.assertEqual(timestamps[1], timestamps[2])

        then = timestamp.timestamp(time_str=timestamps[0])
        now = timestamp.timestamp()
        self.assertAlmostEqual(then, now, places=1)

        sources = [r.split()[1] for r in result]
        self.assertEqual(sources, record)

    ############################
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
