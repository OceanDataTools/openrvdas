#!/usr/bin/env python3

import sys
import time
import unittest

sys.path.append('.')
from logger.utils import timestamp  # noqa: E402
from logger.transforms.timestamp_transform import TimestampTransform  # noqa: E402


class TestTimestampTransform(unittest.TestCase):

    ############################
    def test_default(self):
        transform = TimestampTransform()

        self.assertIsNone(transform.transform(None))

        result = transform.transform('blah')
        time_str = result.split()[0]
        then = timestamp.timestamp(time_str=time_str)
        now = timestamp.timestamp()

        self.assertAlmostEqual(then, now, places=1)
        self.assertEqual(result.split()[1], 'blah')

    ############################
    def test_list(self):
        transform = TimestampTransform()

        self.assertIsNone(transform.transform(None))

        record = ['foo', 'bar', 'baz']
        result = transform.transform(record)
        timestamps = [r.split()[0] for r in result]
        self.assertEqual(timestamps[0], timestamps[1])
        self.assertEqual(timestamps[1], timestamps[2])

        then = timestamp.timestamp(time_str=timestamps[0])
        now = timestamp.timestamp()
        self.assertAlmostEqual(then, now, places=1)

        sources = [r.split()[1] for r in result]
        self.assertEqual(sources, record)

    ############################
    # Try handing a custom timestamp format (in this case, a date).  It
    # bears mentioning that this test will fail if run exactly at
    # midnight...
    def test_custom(self):
        transform = TimestampTransform(time_format=timestamp.DATE_FORMAT)

        self.assertIsNone(transform.transform(None))

        result = transform.transform('blah')
        today = timestamp.date_str()
        self.assertEqual(result.split()[0], today)
        self.assertEqual(result.split()[1], 'blah')


class TestTimestampTransformNMEA(unittest.TestCase):
    """Tests for use_nmea_timestamp=True."""

    def test_gga_timestamp(self):
        transform = TimestampTransform(use_nmea_timestamp=True)
        record = '$GPGGA,123456.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,,,,*47'
        result = transform.transform(record)
        self.assertIn('12:34:56', result)
        self.assertTrue(result.endswith(record))

    def test_rmc_timestamp(self):
        transform = TimestampTransform(use_nmea_timestamp=True)
        record = ('$GPRMC,083559.00,A,4717.115,N,00833.912,E,'
                  '0.0,0.0,130723,,,A*xx')
        result = transform.transform(record)
        self.assertIn('2023-07-13', result)
        self.assertIn('08:35:59', result)

    def test_zda_timestamp(self):
        transform = TimestampTransform(use_nmea_timestamp=True)
        record = '$GPZDA,160012.71,11,03,2025,00,00*6C'
        result = transform.transform(record)
        self.assertIn('2025-03-11', result)
        self.assertIn('16:00:12', result)

    def test_gll_timestamp(self):
        transform = TimestampTransform(use_nmea_timestamp=True)
        record = '$GPGLL,4916.45,N,12311.12,W,225444.00,A,*xx'
        result = transform.transform(record)
        self.assertIn('22:54:44', result)

    def test_vtg_falls_back_to_last_nmea(self):
        transform = TimestampTransform(use_nmea_timestamp=True)
        gga = '$GPGGA,140000.00,,,,,,,,,,,,,*xx'
        transform.transform(gga)

        vtg = '$GPVTG,054.7,T,034.4,M,005.5,N,010.2,K*xx'
        result = transform.transform(vtg)
        self.assertIn('14:00:00', result)
        self.assertTrue(result.endswith(vtg))

    def test_no_nmea_seen_falls_back_to_system_time(self):
        transform = TimestampTransform(use_nmea_timestamp=True)
        vtg = '$GPVTG,054.7,T,034.4,M,005.5,N,010.2,K*xx'
        result = transform.transform(vtg)
        # Should get a system timestamp (approximately now)
        ts_str = result.split(' ', 1)[0]
        ts_val = timestamp.timestamp(time_str=ts_str)
        self.assertAlmostEqual(ts_val, timestamp.timestamp(), places=1)

    def test_staleness_falls_back_to_system_time(self):
        transform = TimestampTransform(
            use_nmea_timestamp=True, nmea_timestamp_timeout=2)
        gga = '$GPGGA,140000.00,,,,,,,,,,,,,*xx'
        transform.transform(gga)

        # Simulate stale timestamp
        transform.nmea_extractor.last_nmea_system_time = time.time() - 10

        vtg = '$GPVTG,054.7,T,034.4,M,005.5,N,010.2,K*xx'
        result = transform.transform(vtg)
        ts_str = result.split(' ', 1)[0]
        ts_val = timestamp.timestamp(time_str=ts_str)
        self.assertAlmostEqual(ts_val, timestamp.timestamp(), places=1)

    def test_disabled_by_default(self):
        """Without use_nmea_timestamp, GGA gets system time, not NMEA time."""
        transform = TimestampTransform()
        record = '$GPGGA,000000.00,,,,,,,,,,,,,*xx'
        result = transform.transform(record)
        ts_str = result.split(' ', 1)[0]
        ts_val = timestamp.timestamp(time_str=ts_str)
        now = timestamp.timestamp()
        self.assertAlmostEqual(ts_val, now, places=1)

    def test_pashr_timestamp(self):
        """Proprietary PASHR sentence should extract NMEA time."""
        transform = TimestampTransform(use_nmea_timestamp=True)
        record = ('$PASHR,113000.00,123.4,T,1.2,-0.5,'
                  '0.3,0.1,0.1,0.2,1,0*xx')
        result = transform.transform(record)
        self.assertIn('11:30:00', result)
        self.assertTrue(result.endswith(record))

    def test_psxn26_timestamp(self):
        """PSXN,26 with separate Y/M/D/H/M/S fields."""
        transform = TimestampTransform(use_nmea_timestamp=True)
        record = '$PSXN,26,2025,03,15,09,15,00.50*xx'
        result = transform.transform(record)
        self.assertIn('2025-03-15', result)
        self.assertIn('09:15:00', result)

    def test_gbs_timestamp(self):
        """Standard GBS sentence should extract NMEA time."""
        transform = TimestampTransform(use_nmea_timestamp=True)
        record = '$GPGBS,091500.00,1.2,3.4,5.6,7,,1.8,2.3*xx'
        result = transform.transform(record)
        self.assertIn('09:15:00', result)
        self.assertTrue(result.endswith(record))


if __name__ == '__main__':
    unittest.main()
