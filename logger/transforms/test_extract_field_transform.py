#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.extract_field_transform import ExtractFieldTransform  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402


class TestExtractFieldTransform(unittest.TestCase):

    ############################
    def test_basic(self):
        t = ExtractFieldTransform('f1')
        self.assertEqual(t.transform({'fields': {'f1': 5}}), 5)
        self.assertEqual(t.transform({'fields': {'f2': 5}}), None)
        self.assertEqual(t.transform({'f2': 5}), None)
        self.assertEqual(t.transform(DASRecord()), None)
        self.assertEqual(t.transform(DASRecord(fields={'f2': 5})), None)


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
