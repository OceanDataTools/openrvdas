#!/usr/bin/env python3

import logging
import sys
import unittest
import json

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.parse_nmea_transform import ParseNMEATransform  # noqa: E402

# flake8: noqa E501  - don't worry about long lines in sample data

LINES = """gyr1 2017-11-10T01:00:07.737Z $HEROT,0002.9,A*10
grv1 2017-11-10T01:00:08.572Z 01:024303 00
seap 2017-11-04T07:00:33.174207Z $GPGGA,002706.69,3938.138360,S,03732.638933,W,1,09,1.0,-4.90,M,,M,,*66
pguv 2017-11-04T05:12:20.687152Z 080614 170008 .00024 3.949E-4 7.126E-4 -1.556E-3 1.127E-2 -3.994E-4 6.285E-8 5.67E-4 46.6 17.924""".split('\n')

RECORDS = [
    {'data_id': 'gyr1', 'message_type': '$HEROT',
     'timestamp': 1510275607.737000,
     'fields': {'Gyro1RateOfTurn': 2.9}, 'metadata': {}},
    {'data_id': 'grv1', 'message_type': '',
        'timestamp': 1510275608.572000,
        'fields': {'Grav1Error': 0, 'Grav1ValueMg': 24303}, 'metadata': {}},
    {'data_id': 'seap', 'message_type': '$GPGGA',
        'timestamp': 1509778833.174207,
        'fields': {'Seap200Alt': -4.9,
                   'Seap200EorW': 'W',
                   'Seap200FixQuality': 1,
                   'Seap200GPSTime': 2706.69,
                   'Seap200HDOP': 1.0,
                   'Seap200Lat': 3938.13836,
                   'Seap200Lon': 3732.638933,
                   'Seap200NorS': 'S',
                   'Seap200NumSats': 9}, 'metadata': {}},
    {'data_id': 'pguv', 'message_type': '',
        'timestamp': 1509772340.687152,
        'fields': {'GUVDate': 80614,
                   'GUVGroundVoltage': 0.00024,
                   'GUVInputVoltage': 17.924,
                   'GUVIrradiance305': 0.01127,
                   'GUVIrradiance313': -0.001556,
                   'GUVIrradiance320': 0.0003949,
                   'GUVIrradiance340': 0.0007126,
                   'GUVIrradiance380': -0.0003994,
                   'GUVIrradiance395': 0.000567,
                   'GUVIrradiance40': 6.285e-08,
                   'GUVTemp': 46.6,
                   'GUVTime': 170008}, 'metadata': {}}
]

JSON = [
    '{"data_id": "gyr1", "message_type": "$HEROT", "timestamp": 1510275607.737, "fields": {"Gyro1RateOfTurn": 2.9}, "metadata": {}}',
    '{"data_id": "grv1", "message_type": "", "timestamp": 1510275608.572, "fields": {"Grav1ValueMg": 24303, "Grav1Error": 0}, "metadata": {}}',
    '{"data_id": "seap", "message_type": "$GPGGA", "timestamp": 1509778833.174207, "fields": {"Seap200GPSTime": 2706.69, "Seap200Lat": 3938.13836, "Seap200NorS": "S", "Seap200Lon": 3732.638933, "Seap200EorW": "W", "Seap200FixQuality": 1, "Seap200NumSats": 9, "Seap200HDOP": 1.0, "Seap200Alt": -4.9}, "metadata": {}}',
    '{"data_id": "pguv", "message_type": "", "timestamp": 1509772340.687152, "fields": {"GUVDate": 80614, "GUVTime": 170008, "GUVGroundVoltage": 0.00024, "GUVIrradiance320": 0.0003949, "GUVIrradiance340": 0.0007126, "GUVIrradiance313": -0.001556, "GUVIrradiance305": 0.01127, "GUVIrradiance380": -0.0003994, "GUVIrradiance40": 6.285e-08, "GUVIrradiance395": 0.000567, "GUVTemp": 46.6, "GUVInputVoltage": 17.924}, "metadata": {}}'
]


############################
def ordered(obj):
    if isinstance(obj, dict):
        return sorted((k, ordered(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return sorted(ordered(x) for x in obj)
    else:
        return obj


################################################################################
@unittest.skip('The ParseNMEATransform class is deprecated')
class TestParseNMEATransform(unittest.TestCase):

    ############################
    def test_default(self):
        transform = ParseNMEATransform()
        self.assertIsNone(transform.transform(None))

        for i in range(len(LINES)):
            line = LINES[i]
            record = RECORDS[i]
            logging.debug('line: %s', line)
            result = transform.transform(line)
            logging.debug('result: %s', result)

            self.assertEqual(record['data_id'], result.data_id)
            self.assertEqual(record['message_type'], result.message_type)
            self.assertEqual(record['timestamp'], result.timestamp)
            self.assertDictEqual(record['fields'], result.fields)
            self.assertDictEqual(record['metadata'], result.metadata)

    ############################
    def test_json(self):
        transform = ParseNMEATransform(json=True)
        self.assertIsNone(transform.transform(None))

        for i in range(len(LINES)):
            line = LINES[i]
            logging.debug('line: %s', line)
            result = transform.transform(line)
            logging.debug('result: %s', result)

            self.assertEqual(ordered(json.loads(result)), ordered(json.loads(JSON[i])))
            # self.assertEqual(result,JSON[i])


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
