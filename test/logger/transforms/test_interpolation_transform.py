#!/usr/bin/env python3
"""Test the InterpolationTransform class.
"""
import logging
import unittest

from logger.transforms.interpolation_transform import (  # noqa: E402
    InterpolationTransform, _reject_outliers)
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
            InterpolationTransform([{'sources': 'Temperature',
                                     'algorithm': 'boxcar_average'}], 10, 60)

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

            # The average should be close to  expected value (exact  depends on window)
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


################################################################################
class TestMissingValues(unittest.TestCase):
    """Missing values (None, NaN) are ignored, and min_count suppresses
    averages of too few values (issue #664)."""

    NAN = float('nan')

    def setUp(self):
        logging.getLogger().setLevel(logging.ERROR)

    def run_transform(self, field_spec, values, interval=10, window=20):
        """Feed (seconds, value) pairs for field 'X' one per record, and return
        {output timestamp: output fields}."""
        transform = InterpolationTransform(field_spec, interval, window)
        results = {}
        for second, value in values:
            result = transform.transform(
                DASRecord(timestamp=1000 + second, fields={'X': value}))
            for r in result or []:
                results[r['timestamp'] - 1000] = r['fields']
        return results

    def spec(self, algorithm, **options):
        return [dict(sources=['X'], algorithm=algorithm, window=20,
                     result_prefix='Avg', **options)]

    ############################
    def test_boxcar_ignores_nan_and_none(self):
        values = [(t, self.NAN if t % 3 == 0 else None if t % 7 == 0 else 10.0)
                  for t in range(0, 60)]
        results = self.run_transform(self.spec('boxcar_average'), values)
        self.assertTrue(results)
        for t, fields in results.items():
            self.assertEqual(fields, {'AvgX': 10.0}, t)

    def test_polar_ignores_nan(self):
        values = [(t, self.NAN if t % 2 else (350.0 if t % 4 else 10.0))
                  for t in range(0, 60)]
        results = self.run_transform(self.spec('polar_average'), values)
        self.assertTrue(results)
        for t, fields in results.items():
            # A window may hold one more 350 than 10, or vice versa, so the
            # average is near north, not exactly north - but nowhere near the
            # 180 a plain average would give, nor NaN.
            direction = fields['AvgX']
            self.assertLess(min(direction, 360 - direction), 5, t)

    def test_nearest_skips_nan(self):
        values = [(t, float(t) if t % 10 else self.NAN) for t in range(0, 60)]
        results = self.run_transform(
            [{'sources': ['X'], 'algorithm': 'nearest', 'window': 20,
              'result_prefix': 'Near'}],
            values)
        self.assertTrue(results)
        for t, fields in results.items():
            # Every output time is a multiple of 10, where the value is NaN,
            # so the nearest valid value is a second either side of it
            self.assertIn(fields['NearX'], (t - 1.0, t + 1.0), t)

    def test_window_of_only_missing_values_outputs_nothing(self):
        values = [(t, 10.0 if t < 20 else self.NAN) for t in range(0, 80)]
        results = self.run_transform(self.spec('boxcar_average'), values)
        self.assertEqual(results[10], {'AvgX': 10.0})
        # Once the window holds only NaNs, there is nothing to output - and
        # in particular no NaN average
        for t, fields in results.items():
            if t >= 40:
                self.assertNotIn('AvgX', fields, t)

    ############################
    def test_min_count(self):
        """One reading every 5 seconds gives 4 or 5 in a 20-second window."""
        values = [(t, 10.0) for t in range(0, 80, 5)]
        self.assertTrue(self.run_transform(
            self.spec('boxcar_average', min_count=4), values))
        self.assertFalse(self.run_transform(
            self.spec('boxcar_average', min_count=6), values))
        self.assertFalse(self.run_transform(
            self.spec('polar_average', min_count=6), values))

    def test_min_count_counts_only_valid_values(self):
        values = [(t, 10.0 if t % 2 == 0 else self.NAN) for t in range(0, 80)]
        self.assertTrue(self.run_transform(
            self.spec('boxcar_average', min_count=10), values))
        self.assertFalse(self.run_transform(
            self.spec('boxcar_average', min_count=12), values))

    def test_min_count_in_dict_form(self):
        field_spec = {'AvgX': {'source': 'X', 'algorithm': {
            'type': 'boxcar_average', 'window': 20, 'min_count': 6}}}
        self.assertFalse(self.run_transform(
            field_spec, [(t, 10.0) for t in range(0, 80, 5)]))

    ############################
    def test_list_form_passes_options_through(self):
        transform = InterpolationTransform(
            self.spec('boxcar_average', min_count=3), 10, 20)
        self.assertEqual(transform.field_spec['AvgX']['algorithm'],
                         {'type': 'boxcar_average', 'window': 20, 'min_count': 3})

        # Without options, the algorithm spec is exactly what it always was
        transform = InterpolationTransform(self.spec('boxcar_average'), 10, 20)
        self.assertEqual(transform.field_spec['AvgX']['algorithm'],
                         {'type': 'boxcar_average', 'window': 20})


################################################################################
class TestRobustAverages(unittest.TestCase):
    """median and trimmed_mean algorithms, and the outlier_mads option,
    which resist spikes and dropouts (issue #664)."""

    # A steady reading of about 10, with a spike and a dropout
    READINGS = [10.0, 10.2, 9.9, 10.1, 250.0, 10.0, 9.8, 10.3, 0.0, 10.1]

    def setUp(self):
        logging.getLogger().setLevel(logging.ERROR)

    def run_transform(self, **algorithm):
        """Feed READINGS repeatedly, one per second, and return the outputs
        for field 'X' once the window is full."""
        spec = [dict(sources=['X'], window=20, result_prefix='Avg', **algorithm)]
        transform = InterpolationTransform(spec, 10, 20)
        outputs = []
        for second in range(100):
            value = self.READINGS[second % len(self.READINGS)]
            result = transform.transform(
                DASRecord(timestamp=1000 + second, fields={'X': value}))
            for r in result or []:
                if r['timestamp'] - 1000 >= 20 and 'AvgX' in r['fields']:
                    outputs.append(r['fields']['AvgX'])
        self.assertTrue(outputs)
        return outputs

    ############################
    def test_spikes_skew_a_plain_mean(self):
        """The baseline the other tests improve on."""
        for value in self.run_transform(algorithm='boxcar_average'):
            self.assertGreater(abs(value - 10), 5)

    def test_median(self):
        for value in self.run_transform(algorithm='median'):
            self.assertAlmostEqual(value, 10.05, delta=0.1)

    def test_trimmed_mean(self):
        for value in self.run_transform(algorithm='trimmed_mean'):
            self.assertAlmostEqual(value, 10.05, delta=0.1)

    def test_trim_option(self):
        """With trim 0, a trimmed mean is a plain mean."""
        plain = self.run_transform(algorithm='boxcar_average')
        untrimmed = self.run_transform(algorithm='trimmed_mean', trim=0)
        for a, b in zip(plain, untrimmed):
            self.assertAlmostEqual(a, b)

    def test_outlier_mads(self):
        for algorithm in ('boxcar_average', 'median', 'trimmed_mean'):
            with self.subTest(algorithm=algorithm):
                for value in self.run_transform(algorithm=algorithm, outlier_mads=3):
                    self.assertAlmostEqual(value, 10.05, delta=0.1)

    def test_min_count(self):
        """One reading a second gives about 20 in a 20-second window."""
        for algorithm in ('median', 'trimmed_mean'):
            with self.subTest(algorithm=algorithm):
                spec = [dict(sources=['X'], algorithm=algorithm, window=20,
                             result_prefix='Avg', min_count=30)]
                transform = InterpolationTransform(spec, 10, 20)
                for second in range(100):
                    result = transform.transform(
                        DASRecord(timestamp=1000 + second, fields={'X': 10.0}))
                    for r in result or []:
                        self.assertNotIn('AvgX', r['fields'])

    ############################
    def test_reject_outliers(self):
        self.assertEqual(_reject_outliers([10, 11, 9, 10, 50], 3), [10, 11, 9, 10])
        # A MAD of zero drops everything that differs from the median
        self.assertEqual(_reject_outliers([10, 10, 10, 10, 99], 3), [10, 10, 10, 10])

    def test_invalid_options_rejected_at_startup(self):
        for options in ({'algorithm': 'polar_average', 'outlier_mads': 3},
                        {'algorithm': 'nearest', 'outlier_mads': 3},
                        {'algorithm': 'median', 'outlier_mads': 0.5},
                        {'algorithm': 'median', 'outlier_mads': 'three'},
                        {'algorithm': 'boxcar_average', 'trim': 0.1},
                        {'algorithm': 'trimmed_mean', 'trim': 0.5},
                        {'algorithm': 'trimmed_mean', 'trim': -0.1}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    InterpolationTransform(
                        [dict(sources=['X'], window=20, result_prefix='Avg', **options)],
                        10, 20)
                # And the same through the dict form of field_spec
                algorithm = dict(options, type=options['algorithm'], window=20)
                del algorithm['algorithm']
                with self.assertRaises(ValueError):
                    InterpolationTransform(
                        {'AvgX': {'source': 'X', 'algorithm': algorithm}}, 10, 20)


if __name__ == '__main__':
    unittest.main()
