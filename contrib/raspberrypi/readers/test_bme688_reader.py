#!/usr/bin/env python3

import sys
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))
from contrib.raspberrypi.readers.bme688_reader import BME688Reader   # noqa: E402


################################################################################
################################################################################
class TestBME688Reader(unittest.TestCase):
    ############################
    def test_interval(self):
        iterations = 4
        reader = BME688Reader(interval=1)
        now = time.time()
        for i in range(iterations):
            reader.read()
        self.assertAlmostEqual(first=time.time(),
                               second=now + iterations,
                               delta=0.3)

    ############################
    def test_conversions(self):
        reader = BME688Reader()
        f_reader = BME688Reader(temp_in_f=True)
        in_reader = BME688Reader(pressure_in_inches=True)
        record = reader.read()
        f_record = f_reader.read()
        in_record = in_reader.read()

        # Check temp conversion
        self.assertAlmostEqual(
            first=float(record.split()[0]),
            second=(float(f_record.split()[0]) - 32) * 5 / 9,
            delta=0.5)

        # Check pressure conversion
        self.assertAlmostEqual(
            first=float(record.split()[2]),
            second=float(in_record.split()[2]) * 33.86389,
            delta=0.1)


if __name__ == '__main__':
    unittest.main()
