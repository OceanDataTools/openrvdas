import unittest
from unittest import mock
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

    def test_conflict_error(self):
        """Test that defining both field_patterns and definition_path raises ValueError."""
        with self.assertRaises(ValueError):
            RegexParseTransform(
                field_patterns=[self.field_pattern],
                definition_path='some/path.yaml'
            )

    @mock.patch('logger.transforms.regex_parse_transform.glob.glob')
    @mock.patch('logger.transforms.regex_parse_transform.read_config.read_config')
    @mock.patch('logger.transforms.regex_parse_transform.read_config.expand_includes')
    def test_definition_path(self, mock_expand, mock_read, mock_glob):
        """Test loading definitions from path with device mapping."""
        # Setup mocks
        mock_glob.return_value = ['/path/to/defs.yaml']

        # Define the mocked configuration structure
        mock_config = {
            'device_types': {
                'TestType': {
                    'format': {
                        'MSG': r'\$(?P<Header>\w+),val=(?P<Val>\d+),rem=(?P<Rem>\w+)'
                    },
                    'fields': {
                        'Val': {'data_type': 'int'},
                        'Header': {'data_type': 'str'}
                    }
                }
            },
            'devices': {
                'dev1': {
                    'device_type': 'TestType',
                    'fields': {
                        'Val': 'Value',   # Resume as Value
                        'Header': 'Head'    # Resume as Head
                        # 'Rem' is NOT mapped, so it should be filtered out
                    }
                }
            }
        }
        mock_read.return_value = mock_config  # simplified, expand_includes usually returns it
        mock_expand.return_value = mock_config

        # Initialize
        transform = RegexParseTransform(definition_path='defs.yaml')

        # Test 1: Known Device (dev1 maps to TestType)
        record = "dev1 2023 $MSG,val=42,rem=FOO"
        result = transform.transform(record)

        self.assertIsNotNone(result)
        # Check renaming: Val -> Value
        self.assertIn('Value', result.fields)
        self.assertEqual(result.fields['Value'], 42)
        self.assertIsInstance(result.fields['Value'], int)  # Converted

        # Check renaming: Header -> Head
        self.assertIn('Head', result.fields)
        self.assertEqual(result.fields['Head'], 'MSG')

        # Check filtering: Rem should be gone (was not in devices fields map)
        self.assertNotIn('Rem', result.fields)

        # Test 2: Unknown Device
        # Should parse with regex but not convert or filter/rename
        record_unk = "unk 2023 $MSG,val=99,rem=BAR"
        # RegexParser extracts data_id if possible, or uses default.
        # Here 'unk' is data_id.
        result_unk = transform.transform(record_unk)

        self.assertIsNotNone(result_unk)
        # Should contain raw keys
        self.assertIn('Val', result_unk.fields)
        self.assertEqual(result_unk.fields['Val'], '99')  # String!
        self.assertIn('Rem', result_unk.fields)  # Present!


if __name__ == '__main__':
    unittest.main()
