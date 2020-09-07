##!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord
from logger.utils import timestamp
from logger.transforms.delta_transform import polar_diff, DeltaTransform

class TestDeltaTransform(unittest.TestCase):

    def test_default(self):
        t = DeltaTransform()
        
        alpha = {'timestamp': 1, 'fields': {'gyroheading': 15}}
        self.assertEqual(t.transform(alpha).fields.get('gyroheading'), None)
        
        t = DeltaTransform(rate=True, field_type={'gyroheading':'polar'})
        beta = {'timestamp': 3, 'fields': {'gyroheading': 359, 'seatemp': 20}}
        results = t.transform(beta)
        
        self.assertEqual(results.fields.get('gyroheading'), -8)
        self.assertEqual(results.fields.get('seatemp'), None)

        t = DeltaTransform()
        # First record, there's nothing to "delta" with
        self.assertEqual(t.transform({'timestamp': 1, 'fields': {'variable': 15}}, None)

        # Second record, at timestamp 2, has a delta of +5
        self.assertEqual(
          t.transform({'timestamp': 2, 'fields': {'variable': 20, 'variable2': 10}}),
                      {'timestamp': 2, 'fields': {'variable': 5, 'variable2': None}})
        # Third record, at timestamp 10, has a delta of -30
        self.assertEqual(
          t.transform({'timestamp': 10, 'fields': {'variable': -10, 'variable2': 15}}),
                      {'timestamp': 10, 'fields': {'variable': -30, 'variable2': 5}})

    def test_polar_diff(self):
        self.assertEqual(polar_diff(5, 10), 5)
        self.assertEqual(polar_diff(10, 5), -5)
        self.assertEqual(polar_diff(5, 359), -6)
        self.assertEqual(polar_diff(359, 5), 6)
        self.assertEqual(polar_diff(90, 269), 179)
        self.assertEqual(polar_diff(90, 271), -179)
        
        
    def test_rate(self):
        t = DeltaTransform(rate=True)
        # First record, there's nothing to "delta" with
        self.assertEqual(t.transform({'timestamp': 1, 'fields': {'variable': 15}}, None)

        # Second record, at timestamp 2, has a delta of +5
        self.assertEqual(
          t.transform({'timestamp': 3, 'fields': {'variable': 20}}),
                      {'timestamp': 3, 'fields': {'variable': 2.5}})
        # Third record, at timestamp 10, has a delta of -30
        self.assertEqual(
          t.transform({'timestamp': 13, 'fields': {'variable': -10}}),
                      {'timestamp': 13, 'fields': {'variable': -3}})
        

if __name__ == '__main__':
    unittest.main()
