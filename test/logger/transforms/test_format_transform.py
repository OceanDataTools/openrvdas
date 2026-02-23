#!/usr/bin/env python3

import logging
import sys
import unittest

sys.path.append('.')
from logger.transforms.format_transform import FormatTransform  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402


class TestFormatTransform(unittest.TestCase):

    ############################
    def test_basic_dict(self):
        # Test basic string formatting with a simple dictionary
        t = FormatTransform(format_str='Values: {a}, {b}')

        # Test successful formatting
        self.assertEqual(t.transform({'fields': {'a': 1, 'b': 2}}), 'Values: 1, 2')

        # Test missing field (should return None by default)
        self.assertEqual(t.transform({'fields': {'a': 1}}), None)

        # Test dictionary without 'fields' key (flat dict)
        self.assertEqual(t.transform({'a': 10, 'b': 20}), 'Values: 10, 20')

    ############################
    def test_basic_das_record(self):
        # Test basic string formatting with DASRecord
        t = FormatTransform(format_str='Temp: {temp}C')

        record = DASRecord(fields={'temp': 23.5})
        self.assertEqual(t.transform(record), 'Temp: 23.5C')

        # Test missing field
        empty_record = DASRecord(fields={'pressure': 1000})
        self.assertEqual(t.transform(empty_record), None)

    ############################
    def test_defaults(self):
        # Test default values for missing fields
        t = FormatTransform(format_str='A: {a}, B: {b}', defaults={'b': 'default_b'})

        # All fields present
        self.assertEqual(t.transform({'fields': {'a': 1, 'b': 2}}), 'A: 1, B: 2')

        # Missing 'b' (should use default)
        self.assertEqual(t.transform({'fields': {'a': 1}}), 'A: 1, B: default_b')

        # Missing 'a' (no default provided -> should return None)
        self.assertEqual(t.transform({'fields': {'b': 2}}), None)

    ############################
    def test_timestamp(self):
        # Test timestamp formatting
        # Using a fixed timestamp for testing: 2023-01-01 12:00:00 UTC = 1672574400
        ts = 1672574400

        # 1. Test raw timestamp (float/int)
        t_raw = FormatTransform(format_str='Time: {timestamp}')
        record = DASRecord(timestamp=ts, fields={})
        self.assertEqual(t_raw.transform(record), f'Time: {ts}')

        # 2. Test ISO timestamp
        t_iso = FormatTransform(format_str='Time: {timestamp}', use_iso_timestamp=True)
        # Note: DASRecord defaults to current time if not provided, so we explicitly provide one
        record = DASRecord(timestamp=ts, fields={})

        # We expect an ISO 8601 string. The exact format depends on logger.utils.timestamp
        # but typically contains the date and time.
        result = t_iso.transform(record)
        self.assertIn('2023-01-01', result)
        self.assertIn('12:00:00', result)

    ############################
    def test_edge_cases(self):
        t = FormatTransform(format_str='Val: {v}')

        # Test with None input (handled by BaseModule digest/process logic)
        self.assertEqual(t.transform(None), None)

        # Test with empty list (handled by BaseModule digest/process logic)
        self.assertEqual(t.transform([]), [])

        # Test with a list of records
        records = [{'fields': {'v': 1}}, {'fields': {'v': 2}}]
        self.assertEqual(t.transform(records), ['Val: 1', 'Val: 2'])


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
