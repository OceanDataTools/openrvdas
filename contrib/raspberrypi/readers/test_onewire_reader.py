#!/usr/bin/env python3

import sys
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))
from contrib.raspberrypi.readers.onewire_reader import OneWireReader   # noqa: E402


################################################################################
################################################################################
class TestOneWireReader(unittest.TestCase):
    ############################
    def test_interval(self):
        iterations = 3
        reader = OneWireReader(interval=1, temp_in_f=True)
        now = time.time()
        for i in range(iterations):
            reader.read()
        self.assertGreater(time.time(), now + iterations)

    ############################
    def test_conversions(self):
        reader = OneWireReader()
        f_reader = OneWireReader(temp_in_f=True)
        record = reader.read().split()
        f_record = f_reader.read().split()

        # Check temp conversion
        for i in range(len(record)):
            self.assertAlmostEqual(
                first=float(record[i]),
                second=(float(f_record[i]) - 32) * 5 / 9,
                delta=0.5)


if __name__ == '__main__':
    unittest.main()
