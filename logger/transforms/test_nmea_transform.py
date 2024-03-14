#!/usr/bin/env python3

# flake8: noqa E501 - ignore long lines

import json
import logging
import pprint
import sys
import tempfile
import time
import unittest
import warnings

from os.path import dirname, realpath

sys.path.append(dirname(realpath(__file__)))
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.nmea_transform import NMEATransform


class TestNMEATransform(unittest.TestCase):
    # set to None to see full diff for long results
    maxDiff = None

    test_records = [
        ({'data_id': 'ship_nav', 'timestamp': 1708644853.370747,
          'fields': {'Latitude': 4404.67098,
                     'Longitude': 11500.0019,
                     'CourseTrue': 1.1,
                     'SpeedOverGround': 8.1,
                     'HeadingTrue': 355.0,
                     'SurfaceCourse': 355.0,
                     'SurfaceSpeed': 7.861768248937385,
                     'DriftCourse': 72.40182954879155,
                     'DriftSpeed': 0.8819736152620004,
                     'Roll': 0.08,
                     'Pitch': 0.65,
                     'Heave': -0.03,
                     'DepthBelowTransducer': 4279.79,
                     'OffsetTransducer': 7.33,
                     'PositionSource': 'posmv'}},
         ['$GPSTN,posmv*05', '$GPDPT,4279.79,7.33*66'])

    ]

    ############################
    def test_nmea_transform(self):
        t = NMEATransform(nmea_list=['STNTransform', 'DPTTransform'],
                          stn_talker_id='GPSTN', id_field='PositionSource',
                          dpt_talker_id='GPDPT', depth_field='DepthBelowTransducer', offset_field='OffsetTransducer')

        for j, (line, expected) in enumerate(self.test_records):
            result = t.transform(line)
            logging.info('expected: %s, result: %s', expected, result)
            self.assertEqual(expected, result)

    def test_bad_nmea_list(self):
        with self.assertLogs(logging.getLogger(), level='INFO') as cm:
            t = NMEATransform(nmea_list=['BADTransform'])
        # Check that the first log message in the output is the one we want
        self.assertIn('BADTransform is not in classes', cm.output[0])


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