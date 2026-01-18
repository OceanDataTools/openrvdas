#!/usr/bin/env python3
import unittest
import json
import sys
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))

from logger.transforms.regex_parse_transform import RegexParseTransform
from logger.utils.das_record import DASRecord

class TestRegexParseTransform(unittest.TestCase):

    def setUp(self):
        self.sample_record = "sensor1 2023-01-01T12:00:00.000Z temp=23.5 humidity=60"
        self.field_pattern = r"temp=(?P<temp>[\d\.]+)\s+humidity=(?P<humidity>[\d\.]+)"

    def test_transform_dict(self):
        """Test transforming to a dictionary (default)."""
        transform = RegexParseTransform(field_patterns=[self.field_pattern])
        result = transform.transform(self.sample_record)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result['data_id'], 'sensor1')
        self.assertEqual(result['fields']['temp'], '23.5')

    def test_transform_das_record(self):
        """Test transforming to a DASRecord."""
        transform = RegexParseTransform(field_patterns=[self.field_pattern], return_das_record=True)
        result = transform.transform(self.sample_record)
        
        self.assertIsInstance(result, DASRecord)
        self.assertEqual(result.data_id, 'sensor1')
        self.assertEqual(result.fields['temp'], '23.5')

    def test_transform_json(self):
        """Test transforming to a JSON string."""
        transform = RegexParseTransform(field_patterns=[self.field_pattern], return_json=True)
        result = transform.transform(self.sample_record)
        
        self.assertIsInstance(result, str)
        parsed = json.loads(result)
        self.assertEqual(parsed['data_id'], 'sensor1')
        self.assertEqual(parsed['fields']['temp'], '23.5')

    def test_data_id_override(self):
        """Test overriding data_id."""
        transform = RegexParseTransform(field_patterns=[self.field_pattern], data_id='my_sensor')
        result = transform.transform(self.sample_record)
        self.assertEqual(result['data_id'], 'my_sensor')

    def test_field_conversion(self):
        """Test integrating with field conversion (float)."""
        # We need to mock or ensure ConvertFieldsTransform logic works.
        # Assuming ConvertFieldsTransform is working (it's imported).
        fields_map = {'temp': 'float'}
        transform = RegexParseTransform(field_patterns=[self.field_pattern], fields=fields_map)
        
        result = transform.transform(self.sample_record)
        # Temp should be a float now, not a string
        self.assertEqual(result['fields']['temp'], 23.5)
        self.assertIsInstance(result['fields']['temp'], float)

if __name__ == '__main__':
    unittest.main()
