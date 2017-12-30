#!/usr/bin/env python3

import logging
import pprint
import sys
import unittest
import warnings

sys.path.append('.')

from logger.utils.das_record import DASRecord
from logger.transforms.true_winds_transform import TrueWindsTransform
from logger.transforms.parse_nmea_transform import ParseNMEATransform

LINES = """mwx1 2017-11-04:05:12:19.537917 PUS,A,071,010.90,M,+340.87,+015.31,60,08
s330 2017-11-04:05:12:20.240177 $INRMC,000000.16,A,3934.831698,S,03727.695242,W,10.8,227.19,070814,18.5,W,A*00
s330 2017-11-04:05:12:20.495430 $INHDT,235.18,T*18
mwx1 2017-11-04:05:12:20.299984 PUS,A,078,010.19,M,+340.85,+015.28,60,0A
s330 2017-11-04:05:12:22.267012 $INRMC,000001.16,A,3934.833674,S,03727.698164,W,10.8,230.21,070814,18.5,W,A*06
mwx1 2017-11-04:05:12:21.058888 PUS,A,080,008.98,M,+340.82,+015.23,60,01
mwx1 2017-11-04:05:12:21.819033 PUS,A,075,009.41,M,+340.99,+015.52,60,02
s330 2017-11-04:05:12:22.520671 $INHDT,235.50,T*14
s330 2017-11-04:05:12:24.285581 $INRMC,000002.16,A,3934.835563,S,03727.701242,W,11.2,232.29,070814,18.5,W,A*01
s330 2017-11-04:05:12:24.539452 $INHDT,235.73,T*15
mwx1 2017-11-04:05:12:22.578922 PUS,A,066,010.76,M,+340.86,+015.30,60,06
mwx1 2017-11-04:05:12:23.338983 PUS,A,063,011.91,M,+340.77,+015.14,60,03
s330 2017-11-04:05:12:26.314871 $INRMC,000003.16,A,3934.837475,S,03727.704471,W,11.6,232.26,070814,18.5,W,A*0C
s330 2017-11-04:05:12:26.567007 $INHDT,235.52,T*16
mwx1 2017-11-04:05:12:24.093591 PUS,A,068,011.14,M,+340.95,+015.45,60,0D
mwx1 2017-11-04:05:12:24.854513 PUS,A,071,008.94,M,+341.11,+015.72,60,0C
s330 2017-11-04:05:12:28.335724 $INRMC,000004.16,A,3934.839517,S,03727.707744,W,11.7,230.17,070814,18.5,W,A*07
s330 2017-11-04:05:12:28.586228 $INHDT,235.02,T*13
mwx1 2017-11-04:05:12:25.615169 PUS,A,080,007.21,M,+341.14,+015.77,60,03
mwx1 2017-11-04:05:12:26.370350 PUS,A,083,007.92,M,+340.94,+015.43,60,06""".split('\n')

RESULTS = [
  None,
  None,
  None,
  {'data_id': 'truw',
   'message_type': 'None',
   'timestamp': 1509772340.299984,
   'fields':{'ApparentWindDir': 313.18,
             'TrueWindDir': 342.66448950069207,
             'TrueWindSpeed': 11.25976276053472},
   'metadata': {}
  },
  None,
  {'data_id': 'truw',
   'message_type': 'None',
   'timestamp': 1509772341.058888,
   'fields':{'ApparentWindDir': 315.18,
             'TrueWindDir': 348.2689627651261,
             'TrueWindSpeed': 10.136863844493519},
   'metadata': {}
  },
  {'data_id': 'truw',
   'message_type': 'None',
   'timestamp': 1509772341.819033,
   'fields':{'ApparentWindDir': 310.18,
             'TrueWindDir': 343.1228501177092,
             'TrueWindSpeed': 10.05993172731625},
   'metadata': {}
  },
  None,
  None,
  None,
  {'data_id': 'truw',
   'message_type': 'None',
   'timestamp': 1509772342.578922,
   'fields':{'ApparentWindDir': 301.73,
             'TrueWindDir': 333.4224730215687,
             'TrueWindSpeed': 10.26784719951879},
   'metadata': {}
  },
  {'data_id': 'truw',
   'message_type': 'None',
   'timestamp': 1509772343.338983,
   'fields':{'ApparentWindDir': 298.73,
             'TrueWindDir': 327.52747400046405,
             'TrueWindSpeed': 10.96297769275824},
   'metadata': {}
  },
  None,
  None,
  {'data_id': 'truw',
   'message_type': 'None',
   'timestamp': 1509772344.093591,
   'fields':{'ApparentWindDir': 303.52,
             'TrueWindDir': 335.0149290175605,
             'TrueWindSpeed': 10.81633764120597},
   'metadata': {}
  },
  {'data_id': 'truw',
   'message_type': 'None',
   'timestamp': 1509772344.854513,
   'fields':{'ApparentWindDir': 306.52,
             'TrueWindDir': 344.6328600199945,
             'TrueWindSpeed': 9.305209500229173},
   'metadata': {}
  },
  None,
  None,
  {'data_id': 'truw',
   'message_type': 'None',
   'timestamp': 1509772345.615169,
   'fields':{'ApparentWindDir': 315.02,
             'TrueWindDir': 356.9663690251725,
             'TrueWindSpeed': 8.967493827016044},
   'metadata': {}
  },
  {'data_id': 'truw',
   'message_type': 'None',
   'timestamp': 1509772346.370350,
   'fields':{'ApparentWindDir': 318.02,
             'TrueWindDir': 356.03324971116865,
             'TrueWindSpeed': 9.765859956501929},
   'metadata': {}
  }
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
    'ApparentWindDir': 0,
    'TrueWindDir': 0,
    'TrueWindSpeed': 0
  },
  {
    'ApparentWindDir': 90,
    'TrueWindDir': 135.0,
    'TrueWindSpeed': 14.142135623730953
  },
  {
    'ApparentWindDir': 0,
    'TrueWindDir': 360,
    'TrueWindSpeed': 20
  },
]

NMEA_RESULTS = [
  None,
  None,
  None,
  'truw 2017-11-04:05:12:20.299984 342.664,11.2598,313.18',
  None,
  'truw 2017-11-04:05:12:21.058888 348.269,10.1369,315.18',
  'truw 2017-11-04:05:12:21.819033 343.123,10.0599,310.18',
  None,
  None,
  None,
  'truw 2017-11-04:05:12:22.578922 333.422,10.2678,301.73',
  'truw 2017-11-04:05:12:23.338983 327.527,10.963,298.73',
  None,
  None,
  'truw 2017-11-04:05:12:24.093591 335.015,10.8163,303.52',
  'truw 2017-11-04:05:12:24.854513 344.633,9.30521,306.52',
  None,
  None,
  'truw 2017-11-04:05:12:25.615169 356.966,8.96749,315.02',
  'truw 2017-11-04:05:12:26.370350 356.033,9.76586,318.02'
]

class TestTrueWindsTransform(unittest.TestCase):
  ############################
  def test_default(self):
    lines = LINES.copy()
    expected_results = RESULTS.copy()
    
    # Use port wind speed, output in m/s
    tw = TrueWindsTransform(data_id='truw',
                            course_fields='S330CourseTrue',
                            speed_fields='S330Speed',
                            heading_fields='S330HeadingTrue',
                            wind_dir_fields='MwxPortRelWindDir',
                            wind_speed_fields='MwxPortRelWindSpeed',
                            convert_speed_factor=0.5144)
    parse = ParseNMEATransform()

    while lines:
      record = parse.transform(lines.pop(0))
      result = tw.transform(record)
      expected = expected_results.pop(0)
      if expected:
        self.assertEqual(result.data_id, 'truw')
        self.assertEqual(result.message_type, None)
        self.assertEqual(result.timestamp, expected['timestamp'])
        self.assertDictEqual(result.fields, expected['fields'])
        self.assertDictEqual(result.metadata, expected['metadata'])
      else:
        self.assertIsNone(result)
    return

  ############################
  def test_sanity(self):
    """Sanity check that the numbers coming out make sense."""
    check = SANITY_CHECK.copy()
    expected_results = SANITY_RESULTS.copy()
    
    tw = TrueWindsTransform(data_id='truw',
                            course_fields='CourseTrue',
                            speed_fields='Speed',
                            heading_fields='HeadingTrue',
                            wind_dir_fields='RelWindDir',
                            wind_speed_fields='RelWindSpeed')

    while check:
      fields = check.pop(0)
      record = DASRecord(data_id='truw', fields=fields)
      result = tw.transform(record)
      logging.debug('sanity result: %s', result)
      expected_fields = expected_results.pop(0)
      self.assertDictEqual(result.fields, expected_fields)

    return

  ############################
  def test_nmea(self):
    lines = LINES.copy()
    expected_results = RESULTS.copy()
    nmea_results = NMEA_RESULTS.copy()
    
    # Use port wind speed, output in m/s
    tw = TrueWindsTransform(data_id='truw',
                            course_fields='S330CourseTrue',
                            speed_fields='S330Speed',
                            heading_fields='S330HeadingTrue',
                            wind_dir_fields='MwxPortRelWindDir',
                            wind_speed_fields='MwxPortRelWindSpeed',
                            convert_speed_factor=0.5144,
                            output_nmea=True)
    parse = ParseNMEATransform()

    while lines:
      record = parse.transform(lines.pop(0))
      result = tw.transform(record)
      nmea_expected = nmea_results.pop(0)
      self.assertEqual(result, nmea_expected)

      # Now check that parsing into a DASRecord works as expected
      das_result = parse.transform(result)
      expected = expected_results.pop(0)
      if das_result is None:
        self.assertEqual(das_result, expected)
      else:
        das_fields = das_result.fields
        exp_fields = expected['fields']
        self.assertAlmostEqual(das_fields['TrueWindDir'],
                               exp_fields['TrueWindDir'], delta=0.001)
        self.assertAlmostEqual(das_fields['TrueWindSpeed'],
                               exp_fields['TrueWindSpeed'], delta=0.001)
        self.assertAlmostEqual(das_fields['ApparentWindDir'],
                               exp_fields['ApparentWindDir'], delta=0.001)
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

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
  
  unittest.main(warnings='ignore')
