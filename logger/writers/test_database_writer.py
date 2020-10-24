#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from database.settings import DATABASE_ENABLED  # noqa: E402
from logger.writers.database_writer import DatabaseWriter  # noqa: E402
from logger.utils.record_parser import RecordParser  # noqa: E402

SAMPLE_DATA = [
    's330 2017-11-04T05:12:19.479303Z $INZDA,000000.17,07,08,2014,,*78',
    's330 2017-11-04T05:12:19.729748Z $INGGA,000000.16,3934.831698,S,03727.695242,W,1,12,0.7,0.82,M,-3.04,M,,*6F',  # noqa: E501
    's330 2017-11-04T05:12:19.984911Z $INVTG,227.19,T,245.64,M,10.8,N,20.0,K,A*36',
    's330 2017-11-04T05:12:20.240177Z $INRMC,000000.16,A,3934.831698,S,03727.695242,W,10.8,227.19,070814,18.5,W,A*00',  # noqa: E501
    's330 2017-11-04T05:12:20.495430Z $INHDT,235.18,T*18',
    's330 2017-11-04T05:12:20.748665Z $PSXN,20,1,0,0,0*3A',
    's330 2017-11-04T05:12:21.000716Z $PSXN,22,-0.05,-0.68*32',
    's330 2017-11-04T05:12:21.256010Z $PSXN,23,-2.82,1.00,235.18,-1.66*3D',
]

SINGLE_RESULTS = [
    {'S330GPSTime': [(1509772339.479303, 0.17)]},
    {'S330GPSDay': [(1509772339.479303, 7)]},
    {'S330GPSMonth': [(1509772339.479303, 8)]},
    {'S330GPSYear': [(1509772339.479303, 2014)]},
    {'S330GPSTime': [(1509772339.729748, 0.16)]},
    {'S330Latitude': [(1509772339.729748, 39.580528)]},
    {'S330NorS': [(1509772339.729748, 'S')]},
    {'S330Longitude': [(1509772339.729748, 37.461587)]},
    {'S330EorW': [(1509772339.729748, 'W')]},
    {'S330FixQuality': [(1509772339.729748, 1)]},
    {'S330NumSats': [(1509772339.729748, 12)]},
    {'S330HDOP': [(1509772339.729748, 0.7)]},
    {'S330AntennaHeight': [(1509772339.729748, 0.82)]},
    {'S330GeoidHeight': [(1509772339.729748, -3.04)]},
    {'S330CourseTrue': [(1509772339.984911, 227.19)]},
    {'S330CourseMag': [(1509772339.984911, 245.64)]},
    {'S330SpeedKt': [(1509772339.984911, 10.8)]},
    {'S330SpeedKm': [(1509772339.984911, 20.0)]},
    {'S330Mode': [(1509772339.984911, 'A')]},
    {'S330GPSTime': [(1509772340.240177, 0.16)]},
    {'S330Latitude': [(1509772340.240177, 39.580528)]},
    {'S330NorS': [(1509772340.240177, 'S')]},
    {'S330Longitude': [(1509772340.240177, 37.461587)]},
    {'S330EorW': [(1509772340.240177, 'W')]},
    {'S330SpeedKt': [(1509772340.240177, 10.8)]},
    {'S330CourseTrue': [(1509772340.240177, 227.19)]},
    {'S330GPSDate': [(1509772340.240177, '070814')]},
    {'S330MagVar': [(1509772340.240177, 18.5)]},
    {'S330MagVarEorW': [(1509772340.240177, 'W')]},
    {'S330Mode': [(1509772340.240177, 'A')]},
    {'S330HeadingTrue': [(1509772340.49543, 235.18)]},
    {'S330HorizQual': [(1509772340.748665, 1)]},
    {'S330HeightQual': [(1509772340.748665, 0)]},
    {'S330HeadingQual': [(1509772340.748665, 0)]},
    {'S330RollPitchQual': [(1509772340.748665, 0)]},
    {'S330GyroCal': [(1509772341.000716, -0.05)]},
    {'S330GyroOffset': [(1509772341.000716, -0.68)]},
    {'S330Roll': [(1509772341.25601, -2.82)]},
    {'S330Pitch': [(1509772341.25601, 1.0)]},
    {'S330HeadingTrue': [(1509772341.25601, 235.18)]},
    {'S330Heave': [(1509772341.25601, -1.66)]}
]


class TestDatabaseWriter(unittest.TestCase):

    ############################
    @unittest.skipUnless(DATABASE_ENABLED, 'Skipping test of DatabaseWriter; '
                         'Database not configured in database/settings.py.')
    def test_database_writer(self):
        parser = RecordParser(definition_path='local/usap/nbp/devices/nbp_devices.yaml',
                              return_das_record=True)
        writer = DatabaseWriter(database='test', host='localhost',
                                user='test', password='test')
        writer.db.exec_sql_command('truncate table data')

        index = 0
        records = [parser.parse_record(s) for s in SAMPLE_DATA]
        for record in records:
            writer.write(record)

            result = True
            while result:
                result = writer.db.read()
                logging.debug('Read %d: %s', index, result)
                if result:
                    self.assertEqual(result, SINGLE_RESULTS[index])
                    index += 1


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
