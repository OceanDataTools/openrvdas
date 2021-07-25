#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.count_transform import CountTransform  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402


class TestCountTransform(unittest.TestCase):
    ############################
    def test_default(self):
        counts = CountTransform()

        self.assertDictEqual(
            counts.transform({'f1': 1, 'f2': 1.5}), {'f1:count': 1, 'f2:count': 1})

        self.assertEqual(
            counts.transform({'f1': 1}), {'f1:count': 2})

        self.assertDictEqual(
            counts.transform({'f1': 1.1, 'f2': 1.5, 'f3': 'string'}),
            {'f1:count': 3, 'f2:count': 2, 'f3:count': 1})

        record = DASRecord(data_id='foo',
                           message_type='bar',
                           fields={'f1': 1.1, 'f2': 1.0})
        result = counts.transform(record)
        self.assertEqual(result.data_id, 'foo_counts')
        self.assertDictEqual(result.fields, {'f1:count': 4, 'f2:count': 3})


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
