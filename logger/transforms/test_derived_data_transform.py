#!/usr/bin/env python3

import logging
import pprint
import sys
import unittest
import warnings

sys.path.append('.')

from logger.transforms.derived_data_transform import *
from logger.transforms.true_winds_transform import TrueWindsTransform
from logger.transforms.parse_nmea_transform import ParseNMEATransform

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

DAS_RECORD_RESULTS = [
  None,
  {'ReciprocalCourse': 47.19},
  {'PortTrueWindDir': 335.177393161606,
   'PortTrueWindSpeed': 11.249182721390321,
   'PortApparentWindDir': 306.18},
  {'PortTrueWindDir': 342.66448950069207,
   'PortTrueWindSpeed': 11.25976276053472,
   'PortApparentWindDir': 313.18},
  {'ReciprocalCourse': 50.21000000000001,
   'PortTrueWindDir': 343.28434098427203,
   'PortTrueWindSpeed': 10.992853771379666,
   'PortApparentWindDir': 313.18},
  {'PortTrueWindDir': 348.2689627651261,
   'PortTrueWindSpeed': 10.136863844493519,
   'PortApparentWindDir': 315.18},
  {'PortTrueWindDir': 343.1228501177092,
   'PortTrueWindSpeed': 10.05993172731625,
   'PortApparentWindDir': 310.18},
  {'PortTrueWindDir': 343.37379038523636,
   'PortTrueWindSpeed': 10.088484891973131,
   'PortApparentWindDir': 310.5},
  {'ReciprocalCourse': 52.28999999999999,
   'PortTrueWindDir': 344.9123243896964,
   'PortTrueWindSpeed': 9.979279490855696,
   'PortApparentWindDir': 310.5},
  {'PortTrueWindDir': 345.0911117416127,
   'PortTrueWindSpeed': 10.000613431316216,
   'PortApparentWindDir': 310.73},
  {'PortTrueWindDir': 333.4224730215687,
   'PortTrueWindSpeed': 10.26784719951879,
   'PortApparentWindDir': 301.73},
  {'PortTrueWindDir': 327.52747400046405,
   'PortTrueWindSpeed': 10.96297769275824,
   'PortApparentWindDir': 298.73},
  {'ReciprocalCourse': 52.25999999999999,
   'PortTrueWindDir': 328.59459759678725,
   'PortTrueWindSpeed': 10.986776999590612,
   'PortApparentWindDir': 298.73},
  {'PortTrueWindDir': 328.39699838501554,
   'PortTrueWindSpeed': 10.965036068189718,
   'PortApparentWindDir': 298.52},
  {'PortTrueWindDir': 335.0149290175605,
   'PortTrueWindSpeed': 10.81633764120597,
   'PortApparentWindDir': 303.52},
  {'PortTrueWindDir': 344.6328600199945,
   'PortTrueWindSpeed': 9.305209500229173,
   'PortApparentWindDir': 306.52},
  {'ReciprocalCourse': 50.16999999999999,
   'PortTrueWindDir': 344.39420954439606,
   'PortTrueWindSpeed': 9.526315883589124,
   'PortApparentWindDir': 306.52},
  {'PortTrueWindDir': 344.02321171966395,
   'PortTrueWindSpeed': 9.478349994953241,
   'PortApparentWindDir': 306.02},
  {'PortTrueWindDir': 356.9663690251725,
   'PortTrueWindSpeed': 8.967493827016044,
   'PortApparentWindDir': 315.02},
  {'PortTrueWindDir': 356.03324971116865,
   'PortTrueWindSpeed': 9.765859956501929,
   'PortApparentWindDir': 318.02}
  ]

FIELD_DICT_RESULT = {
  'PortApparentWindDir': [[1509772340.49543, 313.18],
                          [1509772341.058888, 315.18],
                          [1509772341.819033, 310.18],
                          [1509772342.267012, 310.18],
                          [1509772342.520671, 310.5],
                          [1509772342.578922, 301.5],
                          [1509772343.338983, 298.5],
                          [1509772344.093591, 303.5],
                          [1509772344.285581, 303.5],
                          [1509772344.539452, 303.73],
                          [1509772344.854513, 306.73],
                          [1509772345.615169, 315.73],
                          [1509772346.314871, 315.73],
                          [1509772346.37035, 318.73],
                          [1509772346.567007, 318.52],
                          [1509772348.335724, 318.52],
                          [1509772348.586228, 318.02]],
  'PortTrueWindDir': [[1509772340.49543, 342.66448950069207],
                      [1509772341.058888, 347.4723713118046],
                      [1509772341.819033, 342.45119118341944],
                      [1509772342.267012, 343.1228501177092],
                      [1509772342.520671, 343.37379038523636],
                      [1509772342.578922, 331.87448107212794],
                      [1509772343.338983, 326.14292862772635],
                      [1509772344.093591, 332.6438108004428],
                      [1509772344.285581, 333.93293107275895],
                      [1509772344.539452, 334.13790683910383],
                      [1509772344.854513, 343.6207966334215],
                      [1509772345.615169, 356.8699560667892],
                      [1509772346.314871, 357.95891819933826],
                      [1509772346.37035, 356.98807911745644],
                      [1509772346.567007, 356.8522397659446],
                      [1509772348.335724, 356.3524247053845],
                      [1509772348.586228, 356.03324971116865]],
  'PortTrueWindSpeed': [[1509772340.49543, 11.25976276053472],
                        [1509772341.058888, 10.392527449828384],
                        [1509772341.819033, 10.327233659546385],
                        [1509772342.267012, 10.05993172731625],
                        [1509772342.520671, 10.088484891973131],
                        [1509772342.578922, 10.406287495616924],
                        [1509772343.338983, 11.124789251585174],
                        [1509772344.093591, 10.92584514318212],
                        [1509772344.285581, 10.767855236697343],
                        [1509772344.539452, 10.790498237890521],
                        [1509772344.854513, 9.24571989023819],
                        [1509772345.615169, 8.69973304756972],
                        [1509772346.314871, 8.820678314482505],
                        [1509772346.37035, 9.618336104215334],
                        [1509772346.567007, 9.600346884650742],
                        [1509772348.335724, 9.808338066127327],
                        [1509772348.586228, 9.765859956501929]],
  'ReciprocalCourse': [[1509772340.240177, 47.19],
                       [1509772342.267012, 50.21000000000001],
                       [1509772344.285581, 52.28999999999999],
                       [1509772346.314871, 52.25999999999999],
                       [1509772348.335724, 50.16999999999999]]
}

################################################################################
class TestDerivedDataTransform(unittest.TestCase):

  def test_default(self):
    t = DerivedDataTransform()
    with self.assertRaises(NotImplementedError):
      t.fields()
    with self.assertRaises(NotImplementedError):
      t.transform({})

##############################
# Should be a DerivedDataTransform
class BadTransform(Transform):
  def __init__(self):
    pass
  def fields(self):
    return([])
  def transform(self, value_dict, timestamp_dict=None):
    return {}

##############################
class RecipTransform(DerivedDataTransform):
  def __init__(self):
    pass
  def fields(self):
    return(['S330CourseTrue'])
  def transform(self, value_dict, timestamp_dict=None):
    course = value_dict.get('S330CourseTrue', None)
    if course is None:
      raise ValueError('RecipTransform generated course of "None"')
    recip = course - 180
    if recip < 0:
      recip += 360
    return {'ReciprocalCourse': recip}

################################################################################
class TestComposedDerivedDataTransform(unittest.TestCase):
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
  def test_bad_transform(self):
    bad_transform = BadTransform()
    with self.assertRaises(TypeError):
      t = ComposedDerivedDataTransform(transforms=[bad_transform])

  ############################
  def test_das_record(self):
    """Test using DASRecords as input."""

    parse = ParseNMEATransform()

    recip = RecipTransform()
    port_winds = TrueWindsTransform(course_field='S330CourseTrue',
                                    speed_field='S330Speed',
                                    heading_field='S330HeadingTrue',
                                    wind_dir_field='MwxPortRelWindDir',
                                    wind_speed_field='MwxPortRelWindSpeed',
                                    true_dir_name='PortTrueWindDir',
                                    true_speed_name='PortTrueWindSpeed',
                                    apparent_dir_name='PortApparentWindDir',
                                    convert_speed_factor=0.5144)
    stbd_winds = TrueWindsTransform(course_field='S330CourseTrue',
                                    speed_field='S330Speed',
                                    heading_field='S330HeadingTrue',
                                    wind_dir_field='MwxStbdRelWindDir',
                                    wind_speed_field='MwxStbdRelWindSpeed',
                                    true_dir_name='StbdTrueWindDir',
                                    true_speed_name='StbdTrueWindSpeed',
                                    apparent_dir_name='StbdApparentWindDir',
                                    convert_speed_factor=0.5144)
    t = ComposedDerivedDataTransform(
      transforms=[recip, port_winds, stbd_winds])

    for i in range(len(LINES)):
      line = LINES[i]
      record = parse.transform(line)
      result = t.transform(record)

      expected = DAS_RECORD_RESULTS[i]
      
      logging.info('Input fields: %s', record.fields)
      logging.info('Got result: %s', result)
      logging.info('Expected result: %s', expected)
      if not result or not expected:
        self.assertIsNone(result)
        self.assertIsNone(expected)
      else:
        self.assertRecursiveAlmostEqual(result.fields, expected)

  ############################
  def test_field_dict(self):
    parse = ParseNMEATransform()

    recip = RecipTransform()
    port_winds = TrueWindsTransform(course_field='S330CourseTrue',
                                    speed_field='S330Speed',
                                    heading_field='S330HeadingTrue',
                                    wind_dir_field='MwxPortRelWindDir',
                                    wind_speed_field='MwxPortRelWindSpeed',
                                    true_dir_name='PortTrueWindDir',
                                    true_speed_name='PortTrueWindSpeed',
                                    apparent_dir_name='PortApparentWindDir',
                                    convert_speed_factor=0.5144)
    stbd_winds = TrueWindsTransform(course_field='S330CourseTrue',
                                    speed_field='S330Speed',
                                    heading_field='S330HeadingTrue',
                                    wind_dir_field='MwxStbdRelWindDir',
                                    wind_speed_field='MwxStbdRelWindSpeed',
                                    true_dir_name='StbdTrueWindDir',
                                    true_speed_name='StbdTrueWindSpeed',
                                    apparent_dir_name='StbdApparentWindDir',
                                    convert_speed_factor=0.5144)

    # Test using DASRecords as input
    t = ComposedDerivedDataTransform(
      transforms=[recip, port_winds, stbd_winds])

    field_values = {}
    # Build the field dict
    for i in range(len(LINES)):
      line = LINES[i]
      record = parse.transform(line)
      if not record:
        continue

      for field, value in record.fields.items():
        if not field in field_values:
          field_values[field] = []
        field_values[field].append([record.timestamp, value])

    results = t.transform(field_values)
    self.assertRecursiveAlmostEqual(results, FIELD_DICT_RESULT)
    """
    expected = DAS_RECORD_RESULTS[i]
      
      logging.info('Input fields: %s', record.fields)
      logging.info('Got result: %s', result)
      logging.info('Expected result: %s', expected)
      if not result or not expected:
        self.assertIsNone(result)
        self.assertIsNone(expected)
      else:
        self.assertDictEqual(result.fields, expected)
    """
  
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

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
  
  unittest.main(warnings='ignore')
