#!/usr/bin/env python3
import unittest
import sys
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))

from logger.transforms.regex_parse_transform import RegexParseTransform  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402


class TestRegexParseTransform(unittest.TestCase):

    def setUp(self):
        self.sample_record = "sensor1 2023-01-01T12:00:00.000Z temp=23.5 humidity=60"
        self.field_pattern = r"temp=(?P<temp>[\d\.]+)\s+humidity=(?P<humidity>[\d\.]+)"

    def test_transform(self):
        """Test transforming to a DASRecord (default behavior)."""
        transform = RegexParseTransform(field_patterns=[self.field_pattern])
        result = transform.transform(self.sample_record)

        self.assertIsInstance(result, DASRecord)
        self.assertEqual(result.data_id, 'sensor1')
        self.assertEqual(result.fields['temp'], '23.5')

    def test_data_id_override(self):
        """Test overriding data_id."""
        transform = RegexParseTransform(field_patterns=[self.field_pattern], data_id='my_sensor')
        result = transform.transform(self.sample_record)
        self.assertEqual(result.data_id, 'my_sensor')

    def test_field_conversion(self):
        """Test integrating with field conversion (float)."""
        # We need to mock or ensure ConvertFieldsTransform logic works.
        # Assuming ConvertFieldsTransform is working (it's imported).
        fields_map = {'temp': 'float'}
        transform = RegexParseTransform(field_patterns=[self.field_pattern], fields=fields_map)

        result = transform.transform(self.sample_record)
        # Temp should be a float now, not a string
        self.assertEqual(result.fields['temp'], 23.5)
        self.assertIsInstance(result.fields['temp'], float)


if __name__ == '__main__':
    unittest.main()
