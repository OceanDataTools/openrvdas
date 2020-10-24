#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.slice_transform import SliceTransform  # noqa: E402


class TestSliceTransform(unittest.TestCase):

    def test_default(self):
        with self.assertLogs(logging.getLogger(), logging.ERROR):
            with self.assertRaises(ValueError):
                transform = SliceTransform('1.5')
        with self.assertLogs(logging.getLogger(), logging.ERROR):
            with self.assertRaises(ValueError):
                transform = SliceTransform('3,4,a')

        alpha = 'a b c d e f g h i j k l'

        transform = SliceTransform('1')
        self.assertEqual(transform.transform(alpha), 'b')

        transform = SliceTransform('3:5')
        self.assertEqual(transform.transform(alpha), 'd e')

        transform = SliceTransform('-1')
        self.assertEqual(transform.transform(alpha), 'l')

        transform = SliceTransform('-7, -3:-2')
        self.assertEqual(transform.transform(alpha), 'f j')

        transform = SliceTransform(':3,5:7,9,11:')
        self.assertEqual(transform.transform(alpha), 'a b c f g j l')

        transform = SliceTransform(':')
        self.assertEqual(transform.transform(alpha), alpha)

        transform = SliceTransform('')
        self.assertEqual(transform.transform(alpha), alpha)


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

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
