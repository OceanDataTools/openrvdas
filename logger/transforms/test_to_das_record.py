#!/usr/bin/env python3

import logging
import sys
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.to_das_record_transform import ToDASRecordTransform  # noqa: E402


class TestToDASRecordTransform(unittest.TestCase):
    ############################
    def test_field_name(self):
        t = ToDASRecordTransform(data_id='my_data_id', field_name='my_field_name')
        das_record = t.transform('my_value')
        self.assertAlmostEqual(das_record.timestamp, time.time(), delta=0.001)
        self.assertEqual(das_record.data_id, 'my_data_id')
        self.assertDictEqual(das_record.fields, {'my_field_name': 'my_value'})

        das_record = t.transform(['this should show up as a field value'])
        self.assertEqual(das_record[0].fields.get('my_field_name', None),
                         'this should show up as a field value')

    ############################
    def test_no_field_name(self):
        t = ToDASRecordTransform(data_id='my_data_id')
        das_record = t.transform({'f1': 'v1', 'f2': 'v2'})
        self.assertAlmostEqual(das_record.timestamp, time.time(), delta=0.001)
        self.assertEqual(das_record.data_id, 'my_data_id')
        self.assertDictEqual(das_record.fields, {'f1': 'v1', 'f2': 'v2'})

        with self.assertLogs(level='WARNING'):
            das_record = t.transform('this should log a warning')
        self.assertEqual(das_record, None)

        with self.assertLogs(level='WARNING'):
            das_record = t.transform(['this should log a warning'])
        self.assertEqual(das_record, [None])


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
