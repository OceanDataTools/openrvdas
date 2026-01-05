#!/usr/bin/env python3

import logging
import re
import sys
import unittest

sys.path.append('.')
from logger.transforms.regex_replace_transform import RegexReplaceTransform  # noqa: E402


class TestRegexReplaceTransform(unittest.TestCase):

    def test_basic_replacement(self):
        # Simple string replacement
        t = RegexReplaceTransform(patterns={'foo': 'bar'})
        self.assertEqual(t.transform('foo baz'), 'bar baz')
        self.assertEqual(t.transform('no match here'), 'no match here')
        self.assertIsNone(t.transform(None))

    def test_regex_replacement(self):
        # Regex groups replacement
        # Use raw strings (r'') to avoid invalid escape sequence warnings
        t = RegexReplaceTransform(patterns={r'(\d+)': r'<\1>'})
        self.assertEqual(t.transform('Price: 100'), 'Price: <100>')

        t2 = RegexReplaceTransform(patterns={r'\s+': '-'})
        self.assertEqual(t2.transform('foo   bar'), 'foo-bar')

    def test_multiple_patterns(self):
        # Apply multiple patterns sequentially
        # Note: In Python 3.7+, dict insertion order is preserved.
        # 'a' becomes 'b', then that 'b' (and original 'b's) become 'c'
        patterns = {'a': 'b', 'b': 'c'}
        t = RegexReplaceTransform(patterns=patterns)

        # 'start' -> 'start'
        # 'a' -> 'b' -> 'c'
        # 'b' -> 'c'
        self.assertEqual(t.transform('start a b'), 'stcrt c c')

    def test_flags(self):
        # Test case insensitivity
        t = RegexReplaceTransform(patterns={'foo': 'bar'}, flags=re.IGNORECASE)
        self.assertEqual(t.transform('FOO baz'), 'bar baz')

    def test_count(self):
        # Test limiting the number of replacements
        # Replace only the first occurrence of 'a'
        t = RegexReplaceTransform(patterns={'a': 'b'}, count=1)
        self.assertEqual(t.transform('aaa'), 'baa')


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
