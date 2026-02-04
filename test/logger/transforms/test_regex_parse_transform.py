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

    @mock.patch('logger.utils.read_config.glob.glob')
    @mock.patch('logger.utils.read_config.read_config')
    @mock.patch('logger.utils.read_config.expand_includes')
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

    def test_metadata_injection(self):
        """Test that metadata is injected based on interval."""
        metadata = {'temp': {'units': 'C', 'description': 'Temperature'}}
        # Use a small interval
        transform = RegexParseTransform(
            field_patterns=[self.field_pattern],
            metadata=metadata,
            metadata_interval=10
        )

        # 1. First record (T=100) -> 2023-01-01T00:00:00.000Z
        record_1 = "sensor1 2023-01-01T00:00:00.000Z temp=23.5 humidity=60"
        result_1 = transform.transform(record_1)
        self.assertIsNotNone(result_1.metadata)
        self.assertIn('fields', result_1.metadata)
        self.assertEqual(result_1.metadata['fields']['temp']['units'], 'C')

        # 2. Second record (T+5s) -> 2023-01-01T00:00:05.000Z
        record_2 = "sensor1 2023-01-01T00:00:05.000Z temp=24.0 humidity=61"
        result_2 = transform.transform(record_2)
        # Should NOT have metadata (only 5s elapsed)
        if result_2.metadata:
            self.assertNotIn('fields', result_2.metadata)

        # 3. Third record (T+15s) -> 2023-01-01T00:00:15.000Z
        record_3 = "sensor1 2023-01-01T00:00:15.000Z temp=24.5 humidity=62"
        result_3 = transform.transform(record_3)
        # Should have metadata again (>10s elapsed)
        self.assertIsNotNone(result_3.metadata)
        self.assertIn('fields', result_3.metadata)
        self.assertEqual(result_3.metadata['fields']['temp']['units'], 'C')

    @mock.patch('logger.utils.read_config.glob.glob')
    @mock.patch('logger.utils.read_config.read_config')
    @mock.patch('logger.utils.read_config.expand_includes')
    def test_metadata_compilation(self, mock_expand, mock_read, mock_glob):
        """Test that metadata is correctly compiled from device definitions."""
        mock_glob.return_value = ['/defs.yaml']
        mock_config = {
            'device_types': {
                'TypeA': {
                    'fields': {
                        'RawTemp': {'units': 'C', 'description': 'Raw Temp'}
                    }
                }
            },
            'devices': {
                'sensorA': {
                    'device_type': 'TypeA',
                    'fields': {
                        'RawTemp': 'Temperature'
                    }
                }
            }
        }
        mock_read.return_value = mock_config
        mock_expand.return_value = mock_config

        transform = RegexParseTransform(
            definition_path='defs.yaml',
            metadata_interval=10
        )

        # Check if internal metadata structure was built correctly
        # Mapped field 'Temperature' should have metadata from 'RawTemp'
        # Note: metadata is now in the parser, not the transform
        self.assertIn('Temperature', transform.parser.metadata)
        self.assertEqual(transform.parser.metadata['Temperature']['units'], 'C')
        self.assertEqual(transform.parser.metadata['Temperature']['description'], 'Raw Temp')


if __name__ == '__main__':
    unittest.main()
