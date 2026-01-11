#!/usr/bin/env python3
import unittest
import json
import sys
from os.path import dirname, realpath

# Add the proper path so imports work as if running in the package structure
# path: test/logger/utils/test_regex_parser.py -> root (4 levels up)
sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))

from logger.utils.regex_parser import RegexParser  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402


class TestRegexParser(unittest.TestCase):

    def setUp(self):
        # A simple record: data_id timestamp field_string
        self.sample_record = "sensor1 2023-01-01T12:00:00.000Z temp=23.5 humidity=60"
        self.no_id_record = "2023-01-01T12:00:00.000Z temp=23.5"

        # A pattern to extract fields
        self.field_pattern = r"temp=(?P<temp>[\d\.]+)\s+humidity=(?P<humidity>[\d\.]+)"

    def test_basic_parsing(self):
        """Test standard parsing extracting data_id and timestamp from record."""
        parser = RegexParser(field_patterns=[self.field_pattern])
        result = parser.parse_record(self.sample_record)

        self.assertEqual(result['data_id'], 'sensor1')
        self.assertEqual(result['timestamp'], 1672574400.0)
        self.assertEqual(result['fields']['temp'], '23.5')
        self.assertEqual(result['fields']['humidity'], '60')

    def test_data_id_override(self):
        """Test that passing data_id to __init__ overrides the record's data_id."""
        # Record says 'sensor1', but we initialize with 'override_id'
        parser = RegexParser(field_patterns=[self.field_pattern], data_id='override_id')
        result = parser.parse_record(self.sample_record)

        self.assertEqual(result['data_id'], 'override_id')

    def test_data_id_fallback(self):
        """Test that data_id arg fills in when record has no data_id."""
        # Using a format that doesn't look for data_id at the start
        # e.g., just timestamp and fields
        record_format = r"(?P<timestamp>[0-9TZ:\-\.]*)\s+(?P<field_string>.*)"
        parser = RegexParser(record_format=record_format, data_id='fixed_id')

        result = parser.parse_record(self.no_id_record)
        self.assertEqual(result['data_id'], 'fixed_id')

    def test_unknown_data_id(self):
        """Test default 'unknown' if no data_id in record and no override provided."""
        record_format = r"(?P<timestamp>[0-9TZ:\-\.]*)\s+(?P<field_string>.*)"
        parser = RegexParser(record_format=record_format)  # No data_id arg

        result = parser.parse_record(self.no_id_record)
        self.assertEqual(result['data_id'], 'unknown')

    def test_return_das_record(self):
        """Test returning a DASRecord object."""
        parser = RegexParser(field_patterns=[self.field_pattern], return_das_record=True)
        result = parser.parse_record(self.sample_record)

        self.assertIsInstance(result, DASRecord)
        self.assertEqual(result.data_id, 'sensor1')
        self.assertEqual(result.fields['temp'], '23.5')

    def test_return_json(self):
        """Test returning a JSON string."""
        parser = RegexParser(field_patterns=[self.field_pattern], return_json=True)
        result = parser.parse_record(self.sample_record)

        self.assertIsInstance(result, str)
        parsed_json = json.loads(result)
        self.assertEqual(parsed_json['data_id'], 'sensor1')
        self.assertEqual(parsed_json['fields']['temp'], '23.5')

    def test_message_type_dict(self):
        """Test using a dictionary of message types for field patterns."""
        patterns = {
            'weather': r"temp=(?P<temp>[\d\.]+)",
            'nav': r"lat=(?P<lat>[\d\.]+)"
        }
        parser = RegexParser(field_patterns=patterns)

        # Test matching first pattern
        rec1 = "sensor1 2023-01-01T12:00:00Z temp=23.5"
        res1 = parser.parse_record(rec1)
        self.assertEqual(res1['fields']['temp'], '23.5')

        # Test matching second pattern
        rec2 = "sensor1 2023-01-01T12:00:00Z lat=45.0"
        res2 = parser.parse_record(rec2)
        self.assertEqual(res2['fields']['lat'], '45.0')


if __name__ == '__main__':
    unittest.main()
