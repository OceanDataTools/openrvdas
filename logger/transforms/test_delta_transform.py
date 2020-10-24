#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.delta_transform import polar_diff, DeltaTransform  # noqa: E402


class TestDeltaTransform(unittest.TestCase):
    # Check the polar_diff function we'll be using
    def test_polar_diff(self):
        self.assertEqual(polar_diff(5, 10), 5)
        self.assertEqual(polar_diff(10, 5), -5)
        self.assertEqual(polar_diff(5, 359), -6)
        self.assertEqual(polar_diff(359, 5), 6)
        self.assertEqual(polar_diff(90, 269), 179)
        self.assertEqual(polar_diff(90, 271), -179)

    def test_default(self):
        t = DeltaTransform(field_type={'gyroheading': 'polar'})

        alpha = {'timestamp': 1, 'fields': {'gyroheading': 15}}

        # First time through, no results
        self.assertEqual(t.transform(alpha), None)

        beta = {'timestamp': 3, 'fields': {'gyroheading': 359, 'seatemp': 20}}
        results = t.transform(beta)
        self.assertEqual(results['fields'].get('gyroheading'), -16)
        self.assertEqual(results['fields'].get('seatemp', None), None)

        # Simple transform with no special field types
        t = DeltaTransform()

        # First record, there's nothing to "delta" with
        self.assertEqual(t.transform({'timestamp': 1, 'fields': {'variable': 15}}),
                         None)
        # Second record, at timestamp 2, has a delta of +5
        self.assertEqual(
            t.transform({'timestamp': 2,
                         'fields': {'variable': 20, 'variable2': 10}}),
            {'timestamp': 2, 'fields': {'variable': 5}})
        # Third record, at timestamp 10, has a delta of -30
        self.assertEqual(
            t.transform({'timestamp': 10,
                         'fields': {'variable': -10, 'variable2': 15}}),
            {'timestamp': 10, 'fields': {'variable': -30, 'variable2': 5}})

        # Check that, when given a DASRecord, it returns one
        record = DASRecord(timestamp=11, fields={'variable': -9, 'variable2': 17})
        result = t.transform(record)
        expected = DASRecord(timestamp=11, fields={'variable': 1, 'variable2': 2})
        self.assertEqual(result, expected)

    def test_rate(self):
        t = DeltaTransform(rate=True)
        # First record, there's nothing to "delta" with
        self.assertEqual(
            t.transform({'timestamp': 1, 'fields': {'variable': 15}}), None)

        # Second record, at timestamp 3, has a delta of +5
        self.assertEqual(
            t.transform({'timestamp': 3, 'fields': {'variable': 20}}),
            {'timestamp': 3, 'fields': {'variable': 2.5}})
        # Third record, at timestamp 10, has a delta of -30
        self.assertEqual(
            t.transform({'timestamp': 13, 'fields': {'variable': -10}}),
            {'timestamp': 13, 'fields': {'variable': -3}})

        # Try again, this time with multiple variables and only one of
        # them as a rate.
        t = DeltaTransform(rate=['v1'])
        # First record, there's nothing to "delta" with
        self.assertEqual(
            t.transform({'timestamp': 1, 'fields': {'v1': 15, 'v2': 15}}), None)

        # Second record, at timestamp 3, has a delta of +5
        self.assertEqual(
            t.transform({'timestamp': 3, 'fields': {'v1': 20, 'v2': 20}}),
            {'timestamp': 3, 'fields': {'v1': 2.5, 'v2': 5}})

        # Third record, at timestamp 10, has a delta of -30, and is missing v2
        self.assertEqual(
            t.transform({'timestamp': 13, 'fields': {'v1': -10}}),
            {'timestamp': 13, 'fields': {'v1': -3}})

        # Check that we flag bad timestamps - this should log a warning about
        # encountering negative time, and should return None
        with self.assertLogs(logging.getLogger(), logging.WARNING):
            self.assertEqual(
                t.transform({'timestamp': 1, 'fields': {'v1': -10}}), None)

    def test_args(self):
        # Check that if we're initialized with bad values
        with self.assertRaises(ValueError):
            DeltaTransform(rate=5)
        with self.assertRaises(ValueError):
            DeltaTransform(field_type=5)
        with self.assertRaises(ValueError):
            DeltaTransform(field_type={'v': 'foo'})


if __name__ == '__main__':
    unittest.main()
