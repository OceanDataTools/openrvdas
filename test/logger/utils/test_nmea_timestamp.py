#!/usr/bin/env python3
"""Unit tests for NMEATimestampExtractor."""

import sys
import time
import unittest
from datetime import datetime, timezone

sys.path.append('.')
from logger.utils.nmea_timestamp import NMEATimestampExtractor  # noqa: E402


class TestNMEATimestampExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = NMEATimestampExtractor(timeout=5)

    # ----- GGA -----
    def test_gga(self):
        record = ('$GPGGA,123456.00,4807.038,N,01131.000,E,'
                  '1,08,0.9,545.4,M,,,,*47')
        result = self.extractor.get_timestamp(record)
        self.assertIn('12:34:56', result)

    def test_gga_different_talker(self):
        record = '$INGGA,091500.50,,,,,,,,,,,,,*xx'
        result = self.extractor.get_timestamp(record)
        self.assertIn('09:15:00', result)

    # ----- GLL -----
    def test_gll(self):
        record = '$GPGLL,4916.45,N,12311.12,W,225444.00,A,*xx'
        result = self.extractor.get_timestamp(record)
        self.assertIn('22:54:44', result)

    # ----- RMC -----
    def test_rmc_with_date(self):
        record = ('$GPRMC,083559.00,A,4717.115,N,00833.912,E,'
                  '0.0,0.0,130723,,,A*xx')
        result = self.extractor.get_timestamp(record)
        self.assertIn('2023-07-13', result)
        self.assertIn('08:35:59', result)

    def test_rmc_sets_date_for_subsequent(self):
        """RMC date should be reused by later GGA sentences."""
        rmc = '$GPRMC,120000.00,A,,,,,,,150125,,,A*xx'
        self.extractor.get_timestamp(rmc)

        gga = '$GPGGA,120001.00,,,,,,,,,,,,,*xx'
        result = self.extractor.get_timestamp(gga)
        self.assertIn('2025-01-15', result)
        self.assertIn('12:00:01', result)

    # ----- ZDA -----
    def test_zda(self):
        record = '$GPZDA,160012.71,11,03,2025,00,00*6C'
        result = self.extractor.get_timestamp(record)
        self.assertIn('2025-03-11', result)
        self.assertIn('16:00:12', result)

    def test_zda_sets_date_for_subsequent(self):
        zda = '$GPZDA,100000.00,25,12,2024,00,00*xx'
        self.extractor.get_timestamp(zda)

        gga = '$GPGGA,100001.00,,,,,,,,,,,,,*xx'
        result = self.extractor.get_timestamp(gga)
        self.assertIn('2024-12-25', result)

    # ----- GBS -----
    def test_gbs(self):
        record = '$GPGBS,091500.00,1.2,3.4,5.6,7,,1.8,2.3*xx'
        result = self.extractor.get_timestamp(record)
        self.assertIn('09:15:00', result)

    # ----- GST -----
    def test_gst(self):
        record = '$GPGST,140030.00,1.2,3.4,5.6,7.8,9.0,1.2,3.4*xx'
        result = self.extractor.get_timestamp(record)
        self.assertIn('14:00:30', result)

    # ----- GNS -----
    def test_gns(self):
        record = ('$GNGNS,103000.00,4807.038,N,01131.000,E,'
                  'AN,08,0.9,545.4,47.0,,*xx')
        result = self.extractor.get_timestamp(record)
        self.assertIn('10:30:00', result)

    # ----- BWC -----
    def test_bwc(self):
        record = ('$GPBWC,220000.00,4807.038,N,01131.000,E,'
                  '123.4,T,234.5,M,12.3,N,DEST,A*xx')
        result = self.extractor.get_timestamp(record)
        self.assertIn('22:00:00', result)

    # ----- TLL -----
    def test_tll(self):
        record = ('$RATLL,01,4807.038,N,01131.000,E,'
                  'TARGET,185500.00,T,R*xx')
        result = self.extractor.get_timestamp(record)
        self.assertIn('18:55:00', result)

    # ----- TTM -----
    def test_ttm(self):
        record = ('$RATTM,01,1.23,45.6,T,7.8,90.1,T,2.3,4.5,N,'
                  'TARGET,T,R,061530.00,A*xx')
        result = self.extractor.get_timestamp(record)
        self.assertIn('06:15:30', result)

    # ----- PASHR -----
    def test_pashr(self):
        record = '$PASHR,113000.00,123.4,T,1.2,-0.5,0.3,0.1,0.1,0.2,1,0*xx'
        result = self.extractor.get_timestamp(record)
        self.assertIn('11:30:00', result)

    # ----- PGRMF -----
    def test_pgrmf(self):
        record = ('$PGRMF,1234,567890.0,130723,091500,18,'
                  '4807.038,N,01131.000,E,A,3,12.3,45.6,1.2,3.4*xx')
        result = self.extractor.get_timestamp(record)
        self.assertIn('2023-07-13', result)
        self.assertIn('09:15:00', result)

    # ----- PTNL,GGK -----
    def test_ptnl_ggk(self):
        record = ('$PTNL,GGK,091500.00,130723,'
                  '4807.038,N,01131.000,E,1,08,1.2,45.6*xx')
        result = self.extractor.get_timestamp(record)
        self.assertIn('2023-07-13', result)
        self.assertIn('09:15:00', result)

    # ----- PTNL,PJK -----
    def test_ptnl_pjk(self):
        record = ('$PTNL,PJK,140000.00,250125,'
                  '1234.5,N,6789.0,E,1,08,1.2,45.6*xx')
        result = self.extractor.get_timestamp(record)
        self.assertIn('2025-01-25', result)
        self.assertIn('14:00:00', result)

    # ----- PUBX,00 -----
    def test_pubx00(self):
        record = ('$PUBX,00,170000.00,4807.038,N,01131.000,E,'
                  '545.4,G3,1.2,3.4,0.5,180.0,-0.1,2.3,8,0,0*xx')
        result = self.extractor.get_timestamp(record)
        self.assertIn('17:00:00', result)

    # ----- PUBX,04 -----
    def test_pubx04(self):
        record = ('$PUBX,04,091500.00,130723,'
                  '091500.00,130723,0.0,1234.5,6.7,20.0*xx')
        result = self.extractor.get_timestamp(record)
        self.assertIn('2023-07-13', result)
        self.assertIn('09:15:00', result)

    # ----- PSIMSNS -----
    def test_psimsns(self):
        record = '$PSIMSNS,091500.00,1.2,-0.5,123.4*xx'
        result = self.extractor.get_timestamp(record)
        self.assertIn('09:15:00', result)

    # ----- PSIMSSB -----
    def test_psimssb(self):
        """Time is the last data field; checksum must be stripped."""
        record = '$PSIMSSB,TRANS1,59.123,5.456,100.5,2.3,091500.00*5C'
        result = self.extractor.get_timestamp(record)
        self.assertIn('09:15:00', result)

    # ----- PSXN,26 -----
    def test_psxn26(self):
        record = '$PSXN,26,2025,03,15,09,15,00.50*xx'
        result = self.extractor.get_timestamp(record)
        self.assertIn('2025-03-15', result)
        self.assertIn('09:15:00', result)

    def test_psxn26_sets_date(self):
        """PSXN,26 should set date for subsequent time-only sentences."""
        psxn = '$PSXN,26,2024,06,20,12,00,00.00*xx'
        self.extractor.get_timestamp(psxn)

        gga = '$GPGGA,120001.00,,,,,,,,,,,,,*xx'
        result = self.extractor.get_timestamp(gga)
        self.assertIn('2024-06-20', result)
        self.assertIn('12:00:01', result)

    # ----- Fallback to last observed timestamp -----
    def test_fallback_vtg(self):
        """VTG has no timestamp; should reuse last observed."""
        gga = '$GPGGA,140000.00,,,,,,,,,,,,,*xx'
        self.extractor.get_timestamp(gga)

        vtg = '$GPVTG,054.7,T,034.4,M,005.5,N,010.2,K*xx'
        result = self.extractor.get_timestamp(vtg)
        self.assertIn('14:00:00', result)

    # ----- No timestamp ever seen -----
    def test_no_timestamp_seen_returns_none(self):
        vtg = '$GPVTG,054.7,T,034.4,M,005.5,N,010.2,K*xx'
        result = self.extractor.get_timestamp(vtg)
        self.assertIsNone(result)

    # ----- Non-NMEA record -----
    def test_non_nmea_no_timestamp_seen(self):
        result = self.extractor.get_timestamp('just some text')
        self.assertIsNone(result)

    def test_non_nmea_after_timestamp(self):
        """Non-NMEA text should still get fallback timestamp if available."""
        gga = '$GPGGA,080000.00,,,,,,,,,,,,,*xx'
        self.extractor.get_timestamp(gga)
        result = self.extractor.get_timestamp('plain text')
        # Falls back to last observed NMEA timestamp
        self.assertIn('08:00:00', result)

    # ----- Non-string record -----
    def test_non_string_returns_none(self):
        self.assertIsNone(self.extractor.get_timestamp(None))
        self.assertIsNone(self.extractor.get_timestamp(42))

    # ----- Staleness timeout -----
    def test_staleness_timeout(self):
        gga = '$GPGGA,140000.00,,,,,,,,,,,,,*xx'
        self.extractor.get_timestamp(gga)

        # Simulate time passing beyond timeout
        self.extractor.last_nmea_system_time = time.time() - 10

        vtg = '$GPVTG,054.7,T,034.4,M,005.5,N,010.2,K*xx'
        result = self.extractor.get_timestamp(vtg)
        self.assertIsNone(result)

    # ----- Date fallback to current UTC date -----
    def test_gga_uses_current_date_when_no_date_seen(self):
        gga = '$GPGGA,120000.00,,,,,,,,,,,,,*xx'
        result = self.extractor.get_timestamp(gga)
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        self.assertIn(today, result)

    # ----- Microsecond precision -----
    def test_fractional_seconds(self):
        record = '$GPGGA,123456.78,,,,,,,,,,,,,*xx'
        result = self.extractor.get_timestamp(record)
        self.assertIn('12:34:56.780000', result)

    # ----- Custom time format -----
    def test_custom_time_format(self):
        record = '$GPGGA,093000.00,,,,,,,,,,,,,*xx'
        fmt = '%H:%M:%S'
        result = self.extractor.get_timestamp(record, time_format=fmt)
        self.assertEqual(result, '09:30:00')

    # ----- Cross-sentence date propagation from proprietary -----
    def test_pgrmf_sets_date_for_gga(self):
        """PGRMF date should propagate to subsequent GGA."""
        pgrmf = ('$PGRMF,1234,567890.0,150725,120000,18,'
                 '4807.038,N,01131.000,E,A,3,12.3,45.6,1.2,3.4*xx')
        self.extractor.get_timestamp(pgrmf)

        gga = '$GPGGA,120001.00,,,,,,,,,,,,,*xx'
        result = self.extractor.get_timestamp(gga)
        self.assertIn('2025-07-15', result)

    def test_ptnl_ggk_sets_date_for_gga(self):
        """PTNL,GGK date should propagate to subsequent GGA."""
        ggk = ('$PTNL,GGK,091500.00,010226,'
               '4807.038,N,01131.000,E,1,08,1.2,45.6*xx')
        self.extractor.get_timestamp(ggk)

        gga = '$GPGGA,091501.00,,,,,,,,,,,,,*xx'
        result = self.extractor.get_timestamp(gga)
        self.assertIn('2026-02-01', result)


if __name__ == '__main__':
    unittest.main()
