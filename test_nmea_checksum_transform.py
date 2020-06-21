##!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.transforms.nmea_checksum_transform import NMEAChecksumTransform

class TestNMEAChecksumTransform(unittest.TestCase):
    def test_default(self):
        t = NMEAChecksumTransform()
        
        alpha = '$PSXN,20,1,0,0,0*3A'
        self.assertEqual(t.transform(alpha), alpha)
        
        beta = '$PSXN,20,1,0,0,0*3C'
        self.assertEqual(t.transform(beta), None)

if __name__ == '__main__':
    unittest.main()
