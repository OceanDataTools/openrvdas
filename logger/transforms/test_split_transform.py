#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.split_transform import SplitTransform  # noqa: E402


class TestSplitTransform(unittest.TestCase):

    def test_default(self):
        test_str = '1\n2\n3\n4'
        transform = SplitTransform()
        self.assertEqual(transform.transform(test_str), ['1', '2', '3', '4'])

        test_str = '1ab2ab3ab4ab'
        transform = SplitTransform('ab')
        self.assertEqual(transform.transform(test_str), ['1', '2', '3', '4'])


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
