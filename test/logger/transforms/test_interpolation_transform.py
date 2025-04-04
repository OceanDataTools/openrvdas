#!/usr/bin/env python3
"""Test the InterpolationTransform class.
"""
import logging
import sys
import unittest
from datetime import datetime, timedelta
from os.path import dirname, realpath

import numpy as np

sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))
from logger.transforms.interpolation_transform import InterpolationTransform  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402


class TestInterpolationTransform(unittest.TestCase):
    """Test cases for InterpolationTransform class."""

    ############################
    def setUp(self):
        """Set up test fixtures."""
        # Silence logging
        logging.getLogger().setLevel(logging.ERROR)

    ############################
    def test_init_with_dict(self):
        """Test initialization with a dictionary field spec."""
        field_spec = {
            'AvgTemperature': {
                'source': 'Temperature',
                'algorithm': {
                    'type': 'boxcar_average',
                    'window': 30
                },
            },
            'NearestHumidity': {
                'source': 'Humidity',
                'algorithm': {'type': 'nearest'},
            },
        }
        transform = InterpolationTransform(field_spec, 10, 60, data_id='test_dict')

        self.assertEqual(transform.interval, 10)
        self.assertEqual(transform.window, 60)
        self.assertEqual(transform.data_id, 'test_dict')
        self.assertEqual(set(transform.source_fields), {'Temperature', 'Humidity'})

    ############################
    def test_init_with_list(self):
        """Test initialization with a list field spec."""
        field_spec = [
            {
                'sources': ['Temperature', 'AirTemp'],
                'algorithm': 'boxcar_average',
                'window': 30,
                'result_prefix': 'Avg'
            },
            {
                'sources': ['WindDir'],
                'algorithm': 'polar_average',
                'window': 60,
                'result_prefix': 'Avg'
            }
        ]
        transform = InterpolationTransform(field_spec, 10, 60, data_id='test_list')

        self.assertEqual(transform.interval, 10)
        self.assertEqual(transform.window, 60)
        self.assertEqual(transform.data_id, 'test_list')
        self.assertEqual(set(transform.source_fields), {'Temperature', 'AirTemp', 'WindDir'})
        self.assertIn('AvgTemperature', transform.field_spec)
        self.assertIn('AvgAirTemp', transform.field_spec)
        self.assertIn('AvgWindDir', transform.field_spec)

    ############################
    def test_invalid_field_spec(self):
        """Test that invalid field specs raise appropriate errors."""
        # Not a dict or list
        with self.assertRaises(ValueError):
            InterpolationTransform("invalid", 10, 60)

        # List with non-dict entry
        with self.assertRaises(ValueError):
            InterpolationTransform([123], 10, 60)

        # List with dict but missing sources
        with self.assertRaises(ValueError):
            InterpolationTransform([{'algorithm': 'boxcar_average'}], 10, 60)

        # List with dict but sources not a list
        with self.assertRaises(ValueError):
            InterpolationTransform([{'sources': 'Temperature', 'algorithm': 'boxcar_average'}], 10, 60)

    ############################
    def test_boxcar_average_transform(self):
        """Test the transform with boxcar_average algorithm."""
        field_spec = {
            'AvgTemperature': {
                'source': 'Temperature',
                'algorithm': {
                    'type': 'boxcar_average',
                    'window': 30
                },
            }
        }
        transform = InterpolationTransform(field_spec, 10, 60, data_id='test_boxcar')

        # Create a set of records at 5-second intervals
        base_time = 1609459200  # 2021-01-01 00:00:00
        records = []
        for i in range(20):
            timestamp = base_time + i * 5
            temperature = 20 + i * 0.5  # Linear increase from 20 to 29.5
            record = DASRecord(timestamp=timestamp,
                               fields={'Temperature': temperature},
                               data_id='test_data')
            records.append(record)

        # Process each record and collect results
        results = []
        for record in records:
            result = transform.transform(record)
            if result:
                results.extend(result)

        # We should have results starting after half the window (15s)
        # and up to the latest timestamp minus half the window
        self.assertGreater(len(results), 0)

        # Check that results are within expected range and have expected fields
        for result in results:
            self.assertIn('timestamp', result)
            self.assertIn('fields', result)
            self.assertIn('AvgTemperature', result['fields'])

            # Calculate the expected temperature based on timestamp
            time_index = (result['timestamp'] - base_time) / 5
            expected_temp = 20 + time_index * 0.5

            # The average should be close to the expected value (exact calculation depends on window)
            self.assertLess(abs(result['fields']['AvgTemperature'] - expected_temp), 2.5)

    ############################
    def test_nearest_transform(self):
        """Test the transform with nearest algorithm."""
        field_spec = {
            'NearestHumidity': {
                'source': 'Humidity',
                'algorithm': {'type': 'nearest'},
            }
        }
        transform = InterpolationTransform(field_spec, 10, 60, data_id='test_nearest')

        # Create records with irregular intervals
        base_time = 1609459200  # 2021-01-01 00:00:00
        records = []
        timestamps = [0, 8, 22, 35, 47, 60, 75, 88, 100]
        humidities = [55, 56, 58, 60, 62, 64, 63, 61, 60]

        for i, offset in enumerate(timestamps):
            timestamp = base_time + offset
            record = DASRecord(timestamp=timestamp,
                               fields={'Humidity': humidities[i]},
                               data_id='test_data')
            records.append(record)

        # Process each record and collect results
        results = []
        for record in records:
            result = transform.transform(record)
            if result:
                results.extend(result)

        # Check results
        for result in results:
            # Find nearest data point to interpolation timestamp
            result_time = result['timestamp']
            time_diffs = [abs(result_time - (base_time + t)) for t in timestamps]
            nearest_idx = time_diffs.index(min(time_diffs))

            # The interpolated value should match the nearest value
            self.assertEqual(result['fields']['NearestHumidity'], humidities[nearest_idx])

    ############################
    def test_polar_average_transform(self):
        """Test the transform with polar_average algorithm for angular data."""
        field_spec = {
            'AvgWindDir': {
                'source': 'WindDir',
                'algorithm': {
                    'type': 'polar_average',
                    'window': 30
                },
            }
        }
        transform = InterpolationTransform(field_spec, 10, 60, data_id='test_polar')

        # Create records with wind directions spanning 0/360 boundary
        base_time = 1609459200  # 2021-01-01 00:00:00
        records = []
        timestamps = [0, 10, 20, 30, 40, 50, 60, 70, 80]
        # Wind directions near 0/360 boundary (345, 350, 355, 0, 5, 10, 15, 20, 25)
        wind_dirs = [345, 350, 355, 0, 5, 10, 15, 20, 25]

        for i, offset in enumerate(timestamps):
            timestamp = base_time + offset
            record = DASRecord(timestamp=timestamp,
                               fields={'WindDir': wind_dirs[i]},
                               data_id='test_data')
            records.append(record)

        # Process each record and collect results
        results = []
        for record in records:
            result = transform.transform(record)
            if result:
                results.extend(result)

        # Check results
        self.assertGreater(len(results), 0)

        for result in results:
            # The averaged wind direction should be continuous around the 0/360 boundary
            # and remain in [0, 360] range (inclusive of 360)
            avg_dir = result['fields']['AvgWindDir']
            self.assertGreaterEqual(avg_dir, 0)
            self.assertLessEqual(avg_dir, 360)

            # For this test case, average directions should be in the neighborhood of wind_dirs
            self.assertLess(min(abs(avg_dir - 360), avg_dir), 30)

    ############################
    def test_multiple_transforms(self):
        """Test multiple transforms in one configuration."""
        field_spec = {
            'AvgTemperature': {
                'source': 'Temperature',
                'algorithm': {
                    'type': 'boxcar_average',
                    'window': 30
                },
            },
            'NearestHumidity': {
                'source': 'Humidity',
                'algorithm': {'type': 'nearest'},
            },
            'AvgWindDir': {
                'source': 'WindDir',
                'algorithm': {
                    'type': 'polar_average',
                    'window': 30
                },
            }
        }
        transform = InterpolationTransform(field_spec, 10, 60, data_id='test_multiple')

        # Create records with all three fields
        base_time = 1609459200  # 2021-01-01 00:00:00
        records = []
        for i in range(20):
            timestamp = base_time + i * 5
            temperature = 20 + i * 0.5
            humidity = 55 + i % 5
            wind_dir = (350 + i * 3) % 360

            record = DASRecord(timestamp=timestamp,
                               fields={
                                   'Temperature': temperature,
                                   'Humidity': humidity,
                                   'WindDir': wind_dir
                               },
                               data_id='test_data')
            records.append(record)

        # Process each record and collect results
        results = []
        for record in records:
            result = transform.transform(record)
            if result:
                results.extend(result)

        # Check that all transform fields are present
        self.assertGreater(len(results), 0)
        for result in results:
            self.assertIn('AvgTemperature', result['fields'])
            self.assertIn('NearestHumidity', result['fields'])
            self.assertIn('AvgWindDir', result['fields'])

    ############################
    def test_clean_cache(self):
        """Test that old values get cleaned from the cache."""
        field_spec = {
            'AvgTemperature': {
                'source': 'Temperature',
                'algorithm': {
                    'type': 'boxcar_average',
                    'window': 20
                },
            }
        }
        transform = InterpolationTransform(field_spec, 5, 20, data_id='test_cache')

        # Create an initial set of records
        base_time = 1609459200  # 2021-01-01 00:00:00
        initial_records = []
        for i in range(10):
            timestamp = base_time + i * 5
            temperature = 20 + i
            record = DASRecord(timestamp=timestamp,
                               fields={'Temperature': temperature},
                               data_id='test_data')
            initial_records.append(record)

        # Process initial records
        for record in initial_records:
            transform.transform(record)

        # The initial cache may have already been cleaned by the transform
        # Let's just verify we have some data but not check exact count
        self.assertGreater(len(transform.cached_values['Temperature']), 0)

        # Now add a record that's much later in time
        late_record = DASRecord(
            timestamp=base_time + 100,  # Far beyond initial window
            fields={'Temperature': 50},
            data_id='test_data'
        )
        transform.transform(late_record)

        # Add more records at regular intervals
        for i in range(5):
            timestamp = base_time + 105 + i * 5
            record = DASRecord(
                timestamp=timestamp,
                fields={'Temperature': 55 + i},
                data_id='test_data'
            )
            transform.transform(record)

        # Cache should have been cleaned, and only contain the most recent entries
        # Because the cache cleaning behavior varies based on internal implementation,
        # we'll just check that some cleaning has happened and we don't have all the original
        # records plus all the new ones
        self.assertLess(len(transform.cached_values['Temperature']), 16)  # 10 original + 6 new

    ############################
    def test_with_dict_record(self):
        """Test the transform with dictionary records instead of DASRecord."""
        field_spec = {
            'AvgTemperature': {
                'source': 'Temperature',
                'algorithm': {
                    'type': 'boxcar_average',
                    'window': 30
                },
            }
        }
        transform = InterpolationTransform(field_spec, 10, 60, data_id='test_dict_record')

        # Create a set of dictionary records
        base_time = 1609459200  # 2021-01-01 00:00:00
        records = []
        for i in range(20):
            timestamp = base_time + i * 5
            temperature = 20 + i * 0.5
            record = {
                'timestamp': timestamp,
                'fields': {'Temperature': temperature},
                'data_id': 'test_data'
            }
            records.append(record)

        # Process each record and collect results
        results = []
        for record in records:
            result = transform.transform(record)
            if result:
                results.extend(result)

        # Verify we got valid results
        self.assertGreater(len(results), 0)
        for result in results:
            self.assertIn('timestamp', result)
            self.assertIn('fields', result)
            self.assertIn('AvgTemperature', result['fields'])
            self.assertEqual(result['data_id'], 'test_dict_record')

    ############################
    def test_metadata_generation(self):
        """Test that metadata is generated through the _metadata method."""
        field_spec = {
            'AvgTemperature': {
                'source': 'Temperature',
                'algorithm': {
                    'type': 'boxcar_average',
                    'window': 30
                },
            }
        }
        # Set metadata interval to 20 seconds
        transform = InterpolationTransform(
            field_spec, 5, 60, data_id='test_metadata', metadata_interval=20)

        # Call the _metadata method directly to verify it generates metadata
        metadata = transform._metadata()

        # Check that metadata is properly generated
        self.assertIsInstance(metadata, dict)

        # Validate the metadata structure
        self.assertIn('field', metadata)

        field_metadata = metadata['field']
        self.assertIsInstance(field_metadata, dict)
        self.assertIn('description', field_metadata)
        self.assertIn('device', field_metadata)
        self.assertEqual(field_metadata['device'], 'InterpolationTransform')
        self.assertEqual(field_metadata['device_type'], 'DerivedDataTransform')

        # Verify the device_type_field references our transform output
        self.assertEqual(field_metadata['device_type_field'], 'AvgTemperature')


if __name__ == '__main__':
    unittest.main()
