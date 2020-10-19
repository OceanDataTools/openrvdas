#!/usr/bin/env python

"""
Based on test code developed by: Shawn R. Smith and Mark
A. Bourassa and programmed by: Mylene Remigio
Direct questions about algorithm to:  wocemet@coaps.fsu.edu

Python implementation by David Pablo Cohn (david.cohn@gmail.com)
"""

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))
from logger.utils.truewinds.truew import truew  # noqa: E402

CRSE = [0.0, 0.0, 0.0, 0.0, 180.0, 90.0, 90.0, 225.0, 270.0, 0.0]
CSPD = [0.0, 0.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 3.0, 0.0]
WDIR = [90.0, 90.0, 0.0, 0.0, 180.0, 90.0, 135.0, 270.0, 90.0, 0.0]
HD = [0.0, 90.0, 0.0, 0.0, 180.0, 90.0, 45.0, 225.0, 270.0, 0.0]
WSPD = [5.0, 5.0, 5.0, 0.0, 5.0, 5.0, 5.0, 5.0, 4.0, 0.0]

WMIS = [-1111.0, -9999.0, 1111.0, 9999.0, 5555.0]
ZLR = 0.0

VALUES = [(90.0, 5.0, 90.0),
          (180.0, 5.0, 180.0),
          (0.0, 6.123233995736765e-16, 0.0),
          (180.0, 5.0, 0.0),
          (360.0, 10.0, 0.0),
          (225.0, 7.071067811865475, 180.0),
          (225.0, 7.071067811865475, 180.0),
          (90.0, 7.0710678118654755, 135.0),
          (36.86989764584405, 5.0, 0.0),
          (0, 0, 0)
          ]

BAD_CRSE = [2.0, -1111.0, -2.0, 3.0, 0.0, 0.0, 5.0]
BAD_CSPD = [-9999.0, -9999.0, 8.0, -6.0, 0.0, 0.0, 1.0]
BAD_WDIR = [0.0, 1111.0, 8.0, 0.0, -9.0, 7.0, 2.0]
BAD_HD = [0.0, 5555.0, 8.0, 8.0, 8.0, 8.0, -13.0]
BAD_WSPD = [0.0, 9999.0, 3.0, 3.0, 3.0, -4.0, 2.0]


################################################################################
class TrueWindsTest(unittest.TestCase):
    def test_truew(self):

        for i in range(len(CRSE)):
            (tdir, tspd, adir) = truew(crse=CRSE[i],
                                       cspd=CSPD[i],
                                       hd=HD[i],
                                       wdir=WDIR[i],
                                       wspd=WSPD[i],
                                       zlr=ZLR,
                                       wmis=WMIS)

            self.assertAlmostEqual(tdir, VALUES[i][0], delta=0.0001)
            self.assertAlmostEqual(tspd, VALUES[i][1], delta=0.0001)
            self.assertAlmostEqual(adir, VALUES[i][2], delta=0.0001)

    ############################
    def test_bad_truew(self):
        for i in range(len(BAD_CRSE)):
            with self.assertLogs(logging.getLogger(), logging.WARNING):
                result = truew(crse=BAD_CRSE[i],
                               cspd=BAD_CSPD[i],
                               hd=BAD_HD[i],
                               wdir=BAD_WDIR[i],
                               wspd=BAD_WSPD[i],
                               zlr=ZLR,
                               wmis=WMIS)

            self.assertEqual(result, (None, None, None))


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
