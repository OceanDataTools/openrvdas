#!/usr/bin/env python3

# flake8: noqa E501  - don't worry about long lines in sample data

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.true_winds_transform import TrueWindsTransform  # noqa: E402
from logger.transforms.parse_transform import ParseTransform  # noqa: E402

LINES = """mwx1 2017-11-04T05:12:19.537917Z PUS,A,071,010.90,M,+340.87,+015.31,60,08
s330 2017-11-04T05:12:20.240177Z $INRMC,000000.16,A,3934.831698,S,03727.695242,W,10.8,227.19,070814,18.5,W,A*00
s330 2017-11-04T05:12:20.495430Z $INHDT,235.18,T*18
mwx1 2017-11-04T05:12:20.299984Z PUS,A,078,010.19,M,+340.85,+015.28,60,0A
s330 2017-11-04T05:12:22.267012Z $INRMC,000001.16,A,3934.833674,S,03727.698164,W,10.8,230.21,070814,18.5,W,A*06
mwx1 2017-11-04T05:12:21.058888Z PUS,A,080,008.98,M,+340.82,+015.23,60,01
mwx1 2017-11-04T05:12:21.819033Z PUS,A,075,009.41,M,+340.99,+015.52,60,02
s330 2017-11-04T05:12:22.520671Z $INHDT,235.50,T*14
s330 2017-11-04T05:12:24.285581Z $INRMC,000002.16,A,3934.835563,S,03727.701242,W,11.2,232.29,070814,18.5,W,A*01
s330 2017-11-04T05:12:24.539452Z $INHDT,235.73,T*15
mwx1 2017-11-04T05:12:22.578922Z PUS,A,066,010.76,M,+340.86,+015.30,60,06
mwx1 2017-11-04T05:12:23.338983Z PUS,A,063,011.91,M,+340.77,+015.14,60,03
s330 2017-11-04T05:12:26.314871Z $INRMC,000003.16,A,3934.837475,S,03727.704471,W,11.6,232.26,070814,18.5,W,A*0C
s330 2017-11-04T05:12:26.567007Z $INHDT,235.52,T*16
mwx1 2017-11-04T05:12:24.093591Z PUS,A,068,011.14,M,+340.95,+015.45,60,0D
mwx1 2017-11-04T05:12:24.854513Z PUS,A,071,008.94,M,+341.11,+015.72,60,0C
s330 2017-11-04T05:12:28.335724Z $INRMC,000004.16,A,3934.839517,S,03727.707744,W,11.7,230.17,070814,18.5,W,A*07
s330 2017-11-04T05:12:28.586228Z $INHDT,235.02,T*13
mwx1 2017-11-04T05:12:25.615169Z PUS,A,080,007.21,M,+341.14,+015.77,60,03
mwx1 2017-11-04T05:12:26.370350Z PUS,A,083,007.92,M,+340.94,+015.43,60,06""".split('\n')

RESULTS = [
    None,
    None,
    None,  # {'PortApparentWindDir': 306.18,
    # 'PortTrueWindDir': 335.177393161606,
    # 'PortTrueWindSpeed': 11.249182721390321},
    {'PortApparentWindDir': 313.18,
     'PortTrueWindDir': 342.66448950069207,
     'PortTrueWindSpeed': 11.25976276053472},
    None,
    {'PortApparentWindDir': 315.18,
     'PortTrueWindDir': 348.2689627651261,
     'PortTrueWindSpeed': 10.136863844493519},
    {'PortApparentWindDir': 310.18,
     'PortTrueWindDir': 343.1228501177092,
     'PortTrueWindSpeed': 10.05993172731625},
    None,
    None,
    None,
    {'PortApparentWindDir': 301.73,
     'PortTrueWindDir': 333.4224730215687,
     'PortTrueWindSpeed': 10.26784719951879},
    {'PortApparentWindDir': 298.73,
     'PortTrueWindDir': 327.52747400046405,
     'PortTrueWindSpeed': 10.96297769275824},
    None,
    None,
    {'PortApparentWindDir': 303.52,
     'PortTrueWindDir': 335.0149290175605,
     'PortTrueWindSpeed': 10.81633764120597},
    {'PortApparentWindDir': 306.52,
     'PortTrueWindDir': 344.6328600199945,
     'PortTrueWindSpeed': 9.305209500229173},
    None,
    None,
    {'PortApparentWindDir': 315.02,
     'PortTrueWindDir': 356.9663690251725,
     'PortTrueWindSpeed': 8.967493827016044},
    {'PortApparentWindDir': 318.02,
     'PortTrueWindDir': 356.03324971116865,
     'PortTrueWindSpeed': 9.765859956501929},
]

SANITY_CHECK = [
    {
        'CourseTrue': 0,
        'Speed': 0,
        'HeadingTrue': 0,
        'RelWindDir': 0,
        'RelWindSpeed': 0,
    },
    {
        'CourseTrue': 0,
        'Speed': 10,
        'HeadingTrue': 0,
        'RelWindDir': 90,
        'RelWindSpeed': 10,
    },
    {
        'CourseTrue': 180,
        'Speed': 10,
        'HeadingTrue': 270,
        'RelWindDir': 90,
        'RelWindSpeed': 10,
    },
]
SANITY_RESULTS = [
    {
        'PortApparentWindDir': 0,
        'PortTrueWindDir': 0,
        'PortTrueWindSpeed': 0
    },
    {
        'PortApparentWindDir': 90,
        'PortTrueWindDir': 135.0,
        'PortTrueWindSpeed': 14.142135623730953
    },
    {
        'PortApparentWindDir': 0,
        'PortTrueWindDir': 360,
        'PortTrueWindSpeed': 20
    },
]


class TestTrueWindsTransform(unittest.TestCase):
    ############################
    def assertRecursiveAlmostEqual(self, val1, val2, max_diff=0.00001):
        """Assert that two values/dicts/lists/sets are almost equal. That is,
        that their non-numerical entries are equal, and that their
        numerical entries are equal to within max_diff. NOTE: does not
        detect 'almost' equal for sets.
        """
        if type(val1) in (int, float) and type(val2) in (int, float):
            self.assertLess(abs(val1-val2), max_diff)
            return

        if type(val1) in (str, bool, type(None)):
            self.assertEqual(val1, val2)
            return

        # If here, it should be a list, set or dict
        self.assertTrue(type(val1) in (set, list, dict))
        self.assertEqual(type(val1), type(val2))
        self.assertEqual(len(val1), len(val2))

        if type(val1) == list:
            for i in range(len(val1)):
                self.assertRecursiveAlmostEqual(val1[i], val2[i], max_diff)

        elif type(val1) == set:
            for v in val1:
                self.assertTrue(v in val2)

        elif type(val1) == dict:
            for k in val1:
                self.assertTrue(k in val2)
                self.assertRecursiveAlmostEqual(val1[k], val2[k], max_diff)

    ############################
    def test_default(self):
        lines = LINES.copy()
        expected_results = RESULTS.copy()

        # Use port wind speed, output in m/s
        tw = TrueWindsTransform(course_field='CourseTrue',
                                speed_field='SpeedKt',
                                heading_field='HeadingTrue',
                                wind_dir_field='PortRelWindDir',
                                update_on_fields=['PortRelWindDir'],
                                wind_speed_field='PortRelWindSpeed',
                                true_dir_name='PortTrueWindDir',
                                true_speed_name='PortTrueWindSpeed',
                                apparent_dir_name='PortApparentWindDir',
                                convert_speed_factor=0.5144)
        parse = ParseTransform(
            field_patterns=[
                'PUS,{:nc},{PortRelWindDir:g},{PortRelWindSpeed:g},M,{PortSoundSpeed:g},{PortSonicTemp:g},{PortStatus:d},{Checksum:nc}',
                '$INHDT,{HeadingTrue:f},T*{CheckSum:x}',
                '$INRMC,{GPSTime:f},{GPSStatus:w},{Latitude:nlat},{NorS:w},{Longitude:nlat},{EorW:w},{SpeedKt:f},{CourseTrue:f},{GPSDate:w},{MagneticVar:of},{MagneticVarEorW:ow},{Mode:w}*{Checksum:x}',
            ])

        while lines:
            record = parse.transform(lines.pop(0))

            result_list = tw.transform(record)
            self.assertEqual(type(result_list), list)
            result = result_list[0] if len(result_list) else None

            expected = expected_results.pop(0)
            logging.debug('Got result: %s', result)
            logging.debug('Expected result: %s\n', expected)

            if not result or not expected:
                self.assertIsNone(result)
                self.assertIsNone(expected)
            else:
                logging.debug('Comparing result:\n%s\nwith expected:\n%s',
                              result.fields, expected)
                self.assertRecursiveAlmostEqual(result.fields, expected)

    ############################
    def test_sanity(self):
        """Sanity check that the numbers coming out make sense."""
        check = SANITY_CHECK.copy()
        expected_results = SANITY_RESULTS.copy()

        tw = TrueWindsTransform(course_field='CourseTrue',
                                speed_field='Speed',
                                heading_field='HeadingTrue',
                                wind_dir_field='RelWindDir',
                                wind_speed_field='RelWindSpeed',
                                true_dir_name='PortTrueWindDir',
                                true_speed_name='PortTrueWindSpeed',
                                apparent_dir_name='PortApparentWindDir')

        while check:
            fields = check.pop(0)
            record = DASRecord(data_id='truw', fields=fields)
            result = tw.transform(record)
            if type(result) is list:
                if len(result):
                    result = result[0]
                else:
                    result is None
            expected = expected_results.pop(0)
            logging.info('sanity result: %s', result)
            logging.info('sanity expected: %s', expected)
            self.assertRecursiveAlmostEqual(result.fields, expected)

        return


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
