#!/usr/bin/env python3

import logging
import pprint
import sys
import tempfile
import unittest
import warnings

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord
from logger.transforms.seawater_specific_gravity_transform import SeawaterSpecificGravityTransform
from logger.transforms.parse_transform import ParseTransform

DEVICE_DEF = """
devices:
  sbe45:
    category: "device"
    device_type: "TSG_SBE45"
    description: "SBE45 Thermosalinograph"

    fields:
      Temp: "FlowthroughTemp"
      Conductivity: "Conductivity"
      Salinity: "Salinity"
      SoundVelocity: "SoundVelocity"

device_types:
  TSG_SBE45:
    description: "Thermosalinograph Sea-Bird SBE-45"
    format:
    - "{Temp:og},{Conductivity:og},{Salinity:og},{SoundVelocity:og}"
    - "{Temp:og},{Conductivity:og},{Salinity:og}"
"""

LINES = """sbe45 2019-09-13T00:35:33.283226Z  11.5845,  0.04581,   0.3009, 1453.824
sbe45 2019-09-13T00:35:33.468941Z  11.5838,  0.04581,   0.3009, 1453.821
sbe45 2019-09-13T00:35:34.469202Z  11.5838,  0.04581,   0.3009, 1453.821
sbe45 2019-09-13T00:35:35.468925Z  11.5832,  0.04581,   0.3009, 1453.819
sbe45 2019-09-13T00:35:36.468987Z  11.5828,  0.04581,   0.3009, 1453.817
sbe45 2019-09-13T00:35:37.468965Z  11.5823,  0.04581,   0.3009, 1453.816
sbe45 2019-09-13T00:35:38.468959Z  11.5821,  0.04580,   0.3009, 1453.815
sbe45 2019-09-13T00:35:39.469173Z  11.5816,  0.04580,   0.3009, 1453.813
sbe45 2019-09-13T00:35:40.469232Z  11.5812,  0.04580,   0.3008, 1453.811
sbe45 2019-09-13T00:35:41.469224Z  11.5808,  0.04580,   0.3009, 1453.810""".split('\n')

RESULTS = [
  {'SpecGravity': 1002.3876796350137},
  {'SpecGravity': 1002.3878689434904},
  {'SpecGravity': 1002.3878689434904},
  {'SpecGravity': 1002.388031205312},
  {'SpecGravity': 1002.3881393785334},
  {'SpecGravity': 1002.3882745935676},
  {'SpecGravity': 1002.3883286791171},
  {'SpecGravity': 1002.3884638918299},
  {'SpecGravity': 1002.3884892933784},
  {'SpecGravity': 1002.3886802287215},
]

class TestSeawaterSpecificGravityTransform(unittest.TestCase):
  ############################
  def setUp(self):
    warnings.simplefilter("ignore", ResourceWarning)

    self.tmpdir = tempfile.TemporaryDirectory()
    self.tmpdirname = self.tmpdir.name
    logging.info('created temporary directory "%s"', self.tmpdirname)

    self.device_filename = self.tmpdirname + '/devices.yaml'
    with open(self.device_filename, 'w') as f:
      f.write(DEVICE_DEF)

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

    # Use SBE45 temp and salinity for test. Omit pressure, as we're after
    # surface specific gravity.
    ssg = SeawaterSpecificGravityTransform(temp_field='FlowthroughTemp',
                                           salinity_field='Salinity',
                                           specific_gravity_name='SpecGravity')
    parse = ParseTransform(definition_path=self.device_filename)

    value_dict = {}
    timestamp_dict = {}

    while lines:
      record = parse.transform(lines.pop(0))
      result = ssg.transform(record)
      expected = expected_results.pop(0)
      logging.debug('Got result: %s', result)
      logging.debug('Expected result: %s\n', expected)

      logging.info('Comparing result:\n%s\nwith expected:\n%s',
                   result.fields, expected)
      self.assertRecursiveAlmostEqual(result.fields, expected)

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
