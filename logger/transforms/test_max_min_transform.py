#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.max_min_transform import MaxMinTransform  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402


class TestMaxMinTransform(unittest.TestCase):

    ############################
    def test_default(self):
        max_min = MaxMinTransform()

        self.assertDictEqual(
            max_min.transform({'f1': 1, 'f2': 1.5, 'f3': 'string', 'f4': []}),
            {'f1:max': 1, 'f1:min': 1, 'f2:max': 1.5, 'f2:min': 1.5})

        self.assertEqual(
            max_min.transform({'f1': 1, 'f2': 1.5, 'f3': 'string', 'f4': []}), None)

        self.assertDictEqual(
            max_min.transform({'f1': 1.1, 'f2': 1.5, 'f3': 'string', 'f4': []}),
            {'f1:max': 1.1})

        record = DASRecord(data_id='foo',
                           message_type='bar',
                           fields={'f1': 1.1, 'f2': 1.0, 'f3': 'string', 'f4': []})
        result = max_min.transform(record)
        self.assertEqual(result.data_id, 'foo_limits')
        self.assertDictEqual(result.fields, {'f2:min': 1.0})


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
