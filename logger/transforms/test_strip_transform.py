#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.strip_transform import StripTransform  # noqa: E402


class TestStripTransform(unittest.TestCase):

    def test_default(self):

        alpha = '  abc defg  '
        transform = StripTransform()
        self.assertEqual(transform.transform(alpha), 'abcdefg')
        transform = StripTransform(strip_prefix=True)
        self.assertEqual(transform.transform(alpha), 'abc defg  ')
        transform = StripTransform(strip_suffix=True)
        self.assertEqual(transform.transform(alpha), '  abc defg')
        transform = StripTransform(strip_prefix=True, strip_suffix=True)
        self.assertEqual(transform.transform(alpha), 'abc defg')

        transform = StripTransform(chars=' cd')
        self.assertEqual(transform.transform(alpha), 'abefg')
        transform = StripTransform(chars=' cad', strip_prefix=True)
        self.assertEqual(transform.transform(alpha), 'bc defg  ')

        beta = '\x01\x05abc d\x19'
        transform = StripTransform(unprintable=True)
        self.assertEqual(transform.transform(beta), 'abc d')

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
