##!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord
from logger.utils import timestamp
from logger.transforms.delta_transform import DeltaTransform

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


    def test_polar_diff(self):
        t = DeltaTransform()

        self.assertEqual(t.polar_diff(5, 10), 5)
        self.assertEqual(t.polar_diff(10, 5), -5)
        self.assertEqual(t.polar_diff(5, 359), -6)
        self.assertEqual(t.polar_diff(359, 5), 6)
        self.assertEqual(t.polar_diff(90, 269), 179)
        self.assertEqual(t.polar_diff(90, 271), -179)
        

if __name__ == '__main__':
    unittest.main()
