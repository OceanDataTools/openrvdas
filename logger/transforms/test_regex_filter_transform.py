#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.regex_filter_transform import RegexFilterTransform  # noqa: E402


class TestRegexFilterTransform(unittest.TestCase):

    def test_default(self):
        transform = RegexFilterTransform(pattern='^foo')
        self.assertIsNone(transform.transform(None))
        self.assertIsNone(transform.transform('not foo'))
        self.assertEqual(transform.transform('foo bar'), 'foo bar')

        transform = RegexFilterTransform(pattern='^foo', negate=True)
        self.assertEqual(transform.transform('not foo'), 'not foo')
        self.assertIsNone(transform.transform('foo bar'))

        transform = RegexFilterTransform(pattern='^\dfoo')  # noqa: W605
        self.assertIsNone(transform.transform(None))
        self.assertIsNone(transform.transform('not foo'))
        self.assertEqual(transform.transform('9foo bar'), '9foo bar')

        transform = RegexFilterTransform(pattern='^\dfoo', negate=True)  # noqa: W605
        self.assertEqual(transform.transform('not foo'), 'not foo')
        self.assertIsNone(transform.transform('6foo bar'))

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
