#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.qc_filter_transform import QCFilterTransform  # noqa: E402
from logger.transforms.parse_transform import ParseTransform  # noqa: E402

# flake8: noqa E501  - don't worry about long lines in sample data

LINES = """grv1 2017-11-04T05:12:21.018622Z 01:025876 00
grv1 2017-11-04T05:12:21.273413Z 01:022013 00
grv1 2017-11-04T05:12:21.528747Z 01:021077 00
grv1 2017-11-04T05:12:21.784089Z 01:023624 00
grv1 2017-11-04T05:12:22.034195Z 01:027210 00
grv1 2017-11-04T05:12:22.285414Z 01:029279 00
grv1 2017-11-04T05:12:22.538658Z 01:028207 00
grv1 2017-11-04T05:12:22.794031Z 01:024334 00
grv1 2017-11-04T05:12:23.044427Z 01:020168 00
grv1 2017-11-04T05:12:23.298491Z 01:019470 00""".split('\n')


class TestQCFilterTransform(unittest.TestCase):

    ############################
    def test_default(self):
        p = ParseTransform(field_patterns=['{Units:d}:{GravValue:d} {GravError:d}'])
        q = QCFilterTransform(bounds='GravValue:22000:23000,GravError::2')

        record = p.transform('grv1 2017-11-04T05:12:21.273413Z 01:022013 00')
        self.assertIsNone(q.transform(record))

        record = p.transform('grv1 2017-11-04T05:12:21.273413Z 01:022013 -5')
        self.assertIsNone(q.transform(record))

        record = p.transform('grv1 2017-11-04T05:12:21.273413Z 01:023013 00')
        self.assertEqual(q.transform(record),
                         'GravValue: 23013 > upper bound 23000')

        record = p.transform('grv1 2017-11-04T05:12:21.273413Z 01:023013 03')

        self.assertEqual(q.transform(record).split(';').sort(),
                         'GravValue: 23013 > upper bound 23000; GravError: 3 > upper bound 2'.split(';').sort())

    ############################
    def test_error(self):
        p = ParseTransform(
            field_patterns=['{LF:nc},{LFDepth:of},{LFValid:od},{HF:nc},{HFDepth:of},{HFValid:od},{SoundSpeed:og},{Latitude:f},{Longitude:f}'])
        q = QCFilterTransform(bounds='LFDepth:0:6000,HFDepth:0:5000')

        record = 'knud 2017-11-04T05:12:21.981359Z'
        self.assertEqual(q.transform(record),
                         'Record passed to QCFilterTransform was neither a dict nor a DASRecord. Type was <class \'str\'>: knud 2017-11-04T05:12:21.981359Z')

        record = p.transform(
            'knud 2017-11-04T05:12:21.981359Z 3.5kHz,5146.29,0,,,,1500,-39.583558,-37.466183')
        self.assertEqual(q.transform(record),
                         'HFDepth: non-numeric value: "None"')

    ############################

    def test_message(self):
        q = QCFilterTransform(bounds='LFDepth:0:6000,HFDepth:0:5000',
                              message='The sky is falling!')
        record = {'LFDepth': 5999}
        self.assertEqual(q.transform(record), None)

        record = {'LFDepth': 6001}
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

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
