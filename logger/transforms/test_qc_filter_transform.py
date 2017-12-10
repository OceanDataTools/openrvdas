#!/usr/bin/env python3

import logging
import sys
import unittest
import warnings

sys.path.append('.')

from logger.transforms.qc_filter_transform import QCFilterTransform
from logger.transforms.parse_nmea_transform import ParseNMEATransform

LINES = """grv1 2017-11-04:05:12:21.018622 01:025876 00
grv1 2017-11-04:05:12:21.273413 01:022013 00
grv1 2017-11-04:05:12:21.528747 01:021077 00
grv1 2017-11-04:05:12:21.784089 01:023624 00
grv1 2017-11-04:05:12:22.034195 01:027210 00
grv1 2017-11-04:05:12:22.285414 01:029279 00
grv1 2017-11-04:05:12:22.538658 01:028207 00
grv1 2017-11-04:05:12:22.794031 01:024334 00
grv1 2017-11-04:05:12:23.044427 01:020168 00
grv1 2017-11-04:05:12:23.298491 01:019470 00""".split('\n')

class TestQCFilterTransform(unittest.TestCase):

  ############################
  def test_default(self):
    p = ParseNMEATransform()    
    q = QCFilterTransform(bounds='Grav1ValueMg:22000:23000,Grav1Error::2')

    record = p.transform('grv1 2017-11-04:05:12:21.273413 01:022013 00')
    self.assertIsNone(q.transform(record))

    record = p.transform('grv1 2017-11-04:05:12:21.273413 01:022013 -5')
    self.assertIsNone(q.transform(record))

    record = p.transform('grv1 2017-11-04:05:12:21.273413 01:023013 00')
    self.assertEqual(q.transform(record),
                      'Grav1ValueMg: 23013 > upper bound 23000')

    record = p.transform('grv1 2017-11-04:05:12:21.273413 01:023013 03')

    self.assertEqual(q.transform(record).split(';').sort(),
                     'Grav1ValueMg: 23013 > upper bound 23000; Grav1Error: 3 > upper bound 2'.split(';').sort())

  ############################
  def test_error(self):
    p = ParseNMEATransform()
    q = QCFilterTransform(bounds='KnudLFDepth:0:6000,KnudHFDepth:0:5000')

    record = 'knud 2017-11-04:05:12:21.981359'
    self.assertEqual(q.transform(record),
                     'Improper format record: knud 2017-11-04:05:12:21.981359')

    record = p.transform('knud 2017-11-04:05:12:21.981359 3.5kHz,5146.29,0,,,,1500,-39.583558,-37.466183')
    self.assertEqual(q.transform(record),
                     'KnudHFDepth: non-numeric value: "None"')

  
  ############################
  def test_message(self):
    p = ParseNMEATransform()
    q = QCFilterTransform(bounds='KnudLFDepth:0:6000,KnudHFDepth:0:5000',
                          message='The sky is falling!')

    record = 'knud 2017-11-04:05:12:21.981359'
    self.assertEqual(q.transform(record), 'The sky is falling!')
    
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
