#!/usr/bin/env python3

# flake8: noqa E501  - don't worry about long lines in sample data

import logging
import os
import sys
import tempfile
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.geofence_transform import GeofenceTransform  # noqa: E402

# EEZ of Togo
BOUNDARY_GML = """<?xml version="1.0" encoding="UTF-8"?>
<gml:Polygon xmlns:gml="http://www.opengis.net/gml">
    <gml:exterior>
        <gml:LinearRing>
            <gml:coordinates>
                -0.044915558749550846,-0.044915558749550846 -0.044915558749550846,0.044915558749550846 
                0.044915558749550846,0.044915558749550846 0.044915558749550846,-0.044915558749550846 
                -0.044915558749550846,-0.044915558749550846
            </gml:coordinates>
        </gml:LinearRing>
    </gml:exterior>
</gml:Polygon>"""

LAT_RECORDS = [
    {'lat': -0.07, 'lon': 0},
    {'lat': -0.06, 'lon': 0},
    {'lat': -0.05, 'lon': 0},
    {'lat': -0.04, 'lon': 0},
    {'lat': -0.03, 'lon': 0},
    {'lat': -0.02, 'lon': 0},
    {'lat': -0.02, 'lon': 0.01},
    {'lat': -0.02, 'lon': 0.02},
    {'lat': -0.02, 'lon': 0.03},
    {'lat': -0.02, 'lon': 0.04},
    {'lat': -0.02, 'lon': 0.05},
    {'lat': -0.02, 'lon': 0.06},
    {'lat': -0.02, 'lon': 0.07},
]
LAT_DATA = [
    (-0.07, 0),
    (-0.06, 0),
    (-0.05, 0),
    (-0.04, 0),
    (-0.03, 0),
    (-0.02, 0),
    (-0.02, 0.01),
    (-0.02, 0.02),
    (-0.02, 0.03),
    (-0.02, 0.04),
    (-0.02, 0.05),
    (-0.02, 0.06),
    (-0.02, 0.07),
]

IN_DATA = [
    False, False, False, True, True, True, True, True, True, True, False, False, False
]
BOUNDARY_DATA = [
    False, False, True, True, True, True, True, True, True, True, True, False, False
]

IN_RESULT = [
    'leaving', None, None, 'entering', None, None, None, None, None, None, 'leaving', None, None
]
BOUNDARY_RESULT = [
    'leaving', None, 'entering', None, None, None, None, None, None, None, None, 'leaving', None
]
SECONDS_RESULT = [
    'leaving', None, None, None, 'entering', None, None, None, None, None, 'leaving', None, None
]
class TestGeofenceTransform(unittest.TestCase):
    ############################
    @classmethod
    def setUpClass(cls):
        # Create a temporary file that can be used by all tests in this class
        cls.boundary_file = tempfile.NamedTemporaryFile(mode='w+', delete=False)
        cls.boundary_file.write(BOUNDARY_GML)
        cls.boundary_file.flush()

    ############################
    @classmethod
    def tearDownClass(cls):
        # Close and remove the temporary file after all tests are done
        cls.boundary_file.close()
        os.remove(cls.boundary_file.name)

    ############################
    def test_get_lat_lon(self):
        transform = GeofenceTransform(latitude_field_name='lat',
                                      longitude_field_name='lon',
                                      boundary_file_name=self.boundary_file.name)
        for i in range(len(LAT_RECORDS)):
            self.assertEqual(transform._get_lat_lon(LAT_RECORDS[i]), LAT_DATA[i])
        for i in range(len(LAT_RECORDS)):
            das_record = DASRecord(fields=LAT_RECORDS[i])
            self.assertEqual(transform._get_lat_lon(das_record), LAT_DATA[i])

    ############################
    def test_in_boundary(self):
        transform = GeofenceTransform(latitude_field_name='lat',
                                      longitude_field_name='lon',
                                      boundary_file_name=self.boundary_file.name)
        for i in range(len(LAT_DATA)):
            (lat, lon) = LAT_DATA[i]
            self.assertEqual(transform._is_inside_boundary(lat, lon), IN_DATA[i])

    ############################
    # Should trigger 0.01 degree outside boundary, or appx one data point
    # further out.
    def test_in_boundary_buffer(self):
        transform = GeofenceTransform(latitude_field_name='lat',
                                      longitude_field_name='lon',
                                      boundary_file_name=self.boundary_file.name,
                                      distance_from_boundary_in_degrees=0.01)
        for i in range(len(LAT_DATA)):
            (lat, lon) = LAT_DATA[i]
            is_inside = transform._is_inside_boundary(lat, lon)
            self.assertEqual(is_inside, BOUNDARY_DATA[i],
                             msg=f'_is_inside({lon}/{lat})[{i}] should be {BOUNDARY_DATA[i]}, is {is_inside}')

    ############################
    # Test the whole transform
    def test_transform(self):
        transform = GeofenceTransform(latitude_field_name='lat',
                                      longitude_field_name='lon',
                                      boundary_file_name=self.boundary_file.name,
                                      leaving_boundary_message='leaving',
                                      entering_boundary_message='entering')
        for i in range(len(LAT_RECORDS)):
            record = LAT_RECORDS[i]
            mesg = transform.transform(record)
            self.assertEqual(mesg, IN_RESULT[i],
                             msg=f'transform()[{i}] should be {IN_RESULT[i]}, is {mesg}')

    ############################
    # Should trigger one km outside boundary, or appx one data point
    # further out.
    def test_transform_buffer(self):
        transform = GeofenceTransform(latitude_field_name='lat',
                                      longitude_field_name='lon',
                                      boundary_file_name=self.boundary_file.name,
                                      distance_from_boundary_in_degrees=0.01,
                                      leaving_boundary_message='leaving',
                                      entering_boundary_message='entering')
        for i in range(len(LAT_RECORDS)):
            record = LAT_RECORDS[i]
            mesg = transform.transform(record)
            self.assertEqual(mesg, BOUNDARY_RESULT[i],
                             msg=f'transform()[{i}] should be {BOUNDARY_RESULT[i]}, is {mesg}')

############################
    # Should trigger entry late, due to skipping checks
    def test_transform(self):
        transform = GeofenceTransform(latitude_field_name='lat',
                                      longitude_field_name='lon',
                                      boundary_file_name=self.boundary_file.name,
                                      leaving_boundary_message='leaving',
                                      entering_boundary_message='entering',
                                      seconds_between_checks=0.1)
        for i in range(len(LAT_RECORDS)):
            time.sleep(0.05)
            record = LAT_RECORDS[i]
            mesg = transform.transform(record)
            self.assertEqual(mesg, SECONDS_RESULT[i],
                             msg=f'transform()[{i}] should be {SECONDS_RESULT[i]}, is {mesg}')

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
