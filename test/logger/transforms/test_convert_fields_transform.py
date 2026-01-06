#!/usr/bin/env python3

import logging
import sys
import unittest

sys.path.append('.')
from logger.transforms.convert_fields_transform import ConvertFieldsTransform  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402


class TestConvertFieldsTransform(unittest.TestCase):

    ############################
    def test_simple_conversion(self):
        """Test basic type conversions using the simple string format (float, int, str)."""
        t = ConvertFieldsTransform(fields={
            'heave': 'float',
            'count': 'int',
            'flag': 'str'
        })

        # Test success case
        input_dict = {'heave': '1.23', 'count': '10', 'flag': 123}
        expected = {'heave': 1.23, 'count': 10, 'flag': '123'}
        self.assertDictEqual(t.transform(input_dict), expected)

        # Test partial failure (bad float string)
        # 'bad_val' should remain as is because it fails conversion
        # and delete_unconverted_fields is False by default.
        input_fail = {'heave': 'not_a_number', 'count': '5'}
        expected_fail = {'heave': 'not_a_number', 'count': 5}

        # We expect a warning log for the failed float conversion.
        # assertLogs captures it so it doesn't pollute the console output.
        with self.assertLogs(level='WARNING') as cm:
            self.assertDictEqual(t.transform(input_fail), expected_fail)

            # Verify the correct warning was logged
            self.assertTrue(any("Failed to convert field 'heave'" in log for log in cm.output))

    ############################
    def test_dict_configuration(self):
        """Test configuration where fields are defined as dicts with metadata."""
        # This setup includes extra keys like 'units' and 'description'
        # to ensure the transform ignores them and only uses 'data_type'.
        t = ConvertFieldsTransform(fields={
            'heave': {'data_type': 'float', 'units': 'm'},
            'count': {'data_type': 'int', 'description': 'Number of events'},
            'flag': {'data_type': 'str'}
        })

        input_dict = {'heave': '1.23', 'count': '10', 'flag': 123}
        expected = {'heave': 1.23, 'count': 10, 'flag': '123'}
        self.assertDictEqual(t.transform(input_dict), expected)

        # Ensure that if 'data_type' is missing from the dict, it is ignored gracefully
        t_broken = ConvertFieldsTransform(fields={
            'heave': {'units': 'm'}  # No data_type provided
        })
        input_broken = {'heave': '1.23'}
        # Should remain string because no valid conversion type was found
        expected_broken = {'heave': '1.23'}
        self.assertDictEqual(t_broken.transform(input_broken), expected_broken)

    ############################
    def test_float_string_to_int(self):
        """Test converting a string float ('123.0') to an int."""
        t = ConvertFieldsTransform(fields={'val': 'int'})

        # Case 1: Clean float string
        input_record = {'val': '123.0'}
        expected = {'val': 123}
        self.assertDictEqual(t.transform(input_record), expected)

        # Case 2: Float string with decimals (truncation expected)
        input_trunc = {'val': '123.9'}
        expected_trunc = {'val': 123}
        self.assertDictEqual(t.transform(input_trunc), expected_trunc)

    ############################
    def test_hex_conversion(self):
        """Test converting hex strings to integers."""
        t = ConvertFieldsTransform(fields={
            'flag_a': 'hex',
            'flag_b': 'hex',
            'prefixed': 'hex'
        })

        input_dict = {
            'flag_a': '1A',       # 26
            'flag_b': 'FF',       # 255
            'prefixed': '0x10'    # 16
        }
        expected = {
            'flag_a': 26,
            'flag_b': 255,
            'prefixed': 16
        }
        self.assertDictEqual(t.transform(input_dict), expected)

    ############################
    def test_lat_lon_conversion(self):
        """Test NMEA lat/lon conversion logic."""
        t = ConvertFieldsTransform(lat_lon_fields={
            'latitude': ('raw_lat', 'lat_dir'),
            'longitude': ('raw_lon', 'lon_dir')
        })

        # 45 deg 30 min N = 45.5, 120 deg 30 min W = -120.5
        input_dict = {
            'raw_lat': '4530.00', 'lat_dir': 'N',
            'raw_lon': '12030.00', 'lon_dir': 'W'
        }

        # By default, delete_source_fields is False, so raw fields stay
        result = t.transform(input_dict)
        self.assertAlmostEqual(result['latitude'], 45.5)
        self.assertAlmostEqual(result['longitude'], -120.5)
        self.assertIn('raw_lat', result)
        self.assertIn('lon_dir', result)

    ############################
    def test_delete_options(self):
        """Test delete_source_fields and delete_unconverted_fields."""

        # Case 1: Delete Source Fields = True
        t_del_src = ConvertFieldsTransform(
            lat_lon_fields={'lat': ('raw_lat', 'lat_dir')},
            delete_source_fields=True
        )
        res_src = t_del_src.transform({'raw_lat': '4530.00', 'lat_dir': 'S'})
        self.assertAlmostEqual(res_src['lat'], -45.5)
        self.assertNotIn('raw_lat', res_src)
        self.assertNotIn('lat_dir', res_src)

        # Case 2: Delete Unconverted Fields = True
        t_del_unconv = ConvertFieldsTransform(
            fields={'keep_me': 'int'},
            delete_unconverted_fields=True
        )
        input_dict = {'keep_me': '5', 'ignore_me': 'foo', 'also_ignore': 'bar'}
        res_unconv = t_del_unconv.transform(input_dict)
        self.assertDictEqual(res_unconv, {'keep_me': 5})

        # Case 3: Both True
        # Convert lat/lon, delete raw lat/lon, delete any other fields
        t_both = ConvertFieldsTransform(
            lat_lon_fields={'lat': ('raw_lat', 'lat_dir')},
            delete_source_fields=True,
            delete_unconverted_fields=True
        )
        input_both = {
            'raw_lat': '3000.00', 'lat_dir': 'N',  # Should be converted then deleted
            'extra_field': 'delete_me'  # Should be deleted (unconverted)
        }
        res_both = t_both.transform(input_both)
        self.assertAlmostEqual(res_both['lat'], 30.0)
        self.assertNotIn('raw_lat', res_both)
        self.assertNotIn('extra_field', res_both)
        # Ensure only the new field remains
        self.assertEqual(len(res_both), 1)

    ############################
    def test_das_record_input(self):
        """Test that the transform works on DASRecord objects."""
        t = ConvertFieldsTransform(fields={'val': 'float'})

        record = DASRecord(fields={'val': '9.99', 'other': 'keep'})
        result = t.transform(record)

        self.assertIsInstance(result, DASRecord)
        self.assertEqual(result.fields['val'], 9.99)
        self.assertEqual(result.fields['other'], 'keep')

        # Verify Metadata is preserved
        record.metadata = {'meta': 'data'}
        result = t.transform(record)
        self.assertDictEqual(result.metadata, {'meta': 'data'})

    ############################
    def test_nested_structure(self):
        """Test behavior with 'fields' nested in a dict (common in logger)."""
        t = ConvertFieldsTransform(fields={'a': 'int'})

        # Input format: {'timestamp': 123, 'fields': {'a': '5'}}
        input_record = {'timestamp': 123, 'fields': {'a': '5', 'b': 'ignore'}}
        result = t.transform(input_record)

        self.assertEqual(result['fields']['a'], 5)
        self.assertEqual(result['timestamp'], 123)

    ############################
    def test_empty_result(self):
        """Test that empty results (due to aggressive filtering) return None."""
        t = ConvertFieldsTransform(
            fields={'a': 'int'},
            delete_unconverted_fields=True
        )

        # 'a' is missing, 'b' is unconverted and deleted -> result empty
        input_record = {'b': '10'}
        result = t.transform(input_record)
        self.assertIsNone(result)


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
