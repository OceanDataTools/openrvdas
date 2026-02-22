#!/usr/bin/env python3
"""Extract timestamps from NMEA sentences.

Supports all common NMEA 0183 sentence types that include timestamps,
both standard and proprietary. Tracks the most recent NMEA-derived
timestamp so that non-timestamped sentences (e.g. VTG, HDT) can reuse
it, subject to a configurable staleness timeout.

Supported standard sentences:
    GGA, GLL, RMC, ZDA, GBS, GST, GNS, BWC, TLL, TTM

Supported proprietary sentences:
    PASHR, PGRMF, PTNL GGK/PJK, PUBX 00/04, PSIMSNS, PSIMSSB, PSXN 26
"""

import logging
import re
import time
from datetime import datetime, timezone

from logger.utils import timestamp as ts_util

# Captures the full sentence identifier between $/! and the first comma.
# Works for both standard (e.g. "GPGGA") and proprietary (e.g. "PSIMSNS").
NMEA_PREFIX_RE = re.compile(r'^[$!](\w+),')

# NMEA time field: hhmmss or hhmmss.ss(s).
# No end-of-string anchor so it tolerates residual checksum characters.
NMEA_TIME_RE = re.compile(r'^(\d{2})(\d{2})(\d{2}(?:\.\d+)?)')

# ---------------------------------------------------------------------------
# Sentence lookup tables
#
# Standard sentences are identified by the last 3 characters of a 5-char
# talker+type prefix (e.g. "GPGGA" -> "GGA").  Proprietary sentences are
# identified by their full prefix or by prefix + sub-type field.
#
# Values are the comma-split field index of the time (hhmmss.ss) field.
# ---------------------------------------------------------------------------

# Standard NMEA sentences: 3-char type -> time field index
_STD_TIME = {
    'GGA': 1, 'GLL': 5, 'RMC': 1, 'ZDA': 1,
    'GBS': 1, 'GST': 1, 'GNS': 1, 'BWC': 1,
    'TLL': 7, 'TTM': 14,
}

# Standard sentences carrying a ddmmyy date: type -> date field index
_STD_DATE = {'RMC': 9}

# ZDA carries day/month/year in separate fields
_ZDA_DATE_FIELDS = (2, 3, 4)  # (day_idx, month_idx, year_idx)

# 5-char proprietary sentences (matched by full prefix without $)
_PROP5_TIME = {'PASHR': 1, 'PGRMF': 4}
_PROP5_DATE = {'PGRMF': 3}

# Sub-typed proprietary: (prefix, first-data-field) -> time field index
_SUB_TIME = {
    ('PTNL', 'GGK'): 2, ('PTNL', 'PJK'): 2,
    ('PUBX', '00'): 2, ('PUBX', '04'): 2,
}
_SUB_DATE = {
    ('PTNL', 'GGK'): 3, ('PTNL', 'PJK'): 3,
    ('PUBX', '04'): 3,
}

# Long-name proprietary (>5 chars): full prefix -> time field index
_LONG_TIME = {'PSIMSNS': 1, 'PSIMSSB': 6}


def _strip_checksum(field):
    """Remove ``*checksum`` suffix from a field value."""
    idx = field.find('*')
    return field[:idx] if idx >= 0 else field


class NMEATimestampExtractor:
    """Parse NMEA sentences to extract embedded timestamps."""

    def __init__(self, timeout=1, quiet=False, time_drift_threshold=0.1):
        self.timeout = timeout
        self.quiet = quiet
        self.time_drift_threshold = time_drift_threshold
        self.last_nmea_date = None      # datetime.date from RMC/ZDA/etc.
        self.last_nmea_datetime = None   # full datetime object
        self.last_nmea_system_time = 0   # time.time() of last extraction
        self.seen_timestamp = False

    def get_timestamp(self, record, time_format=ts_util.TIME_FORMAT,
                      time_zone=ts_util.timezone.utc):
        """Return a formatted timestamp string extracted from *record*,
        or fall back to the last observed NMEA timestamp. Returns None
        when no NMEA timestamp is available (caller should use system time).
        """
        if not isinstance(record, str):
            return None

        nmea_dt = self._parse_nmea_datetime(record)
        if nmea_dt is not None:
            now = time.time()
            self.last_nmea_datetime = nmea_dt
            self.last_nmea_system_time = now
            self.seen_timestamp = True
            if not self.quiet and self.time_drift_threshold is not None:
                nmea_epoch = nmea_dt.timestamp()
                drift = abs(nmea_epoch - now)
                if drift > self.time_drift_threshold:
                    logging.warning(
                        'NMEATimestampExtractor: NMEA time differs from '
                        'system time by %.3fs (threshold=%.3fs)',
                        drift, self.time_drift_threshold)
            return nmea_dt.strftime(time_format)

        # Fall back to last observed timestamp
        if not self.seen_timestamp:
            return None

        elapsed = time.time() - self.last_nmea_system_time
        if elapsed > self.timeout:
            if not self.quiet:
                logging.warning(
                    'NMEATimestampExtractor: last NMEA timestamp is %.1fs '
                    'old (timeout=%s); falling back to system time',
                    elapsed, self.timeout)
            return None

        return self.last_nmea_datetime.strftime(time_format)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_nmea_datetime(self, record):
        """Try to extract a datetime from an NMEA sentence.
        Returns a datetime object or None.
        """
        m = NMEA_PREFIX_RE.match(record)
        if not m:
            return None

        prefix = m.group(1).upper()
        fields = record.split(',')

        # 1. Standard 5-char prefix (2-char talker + 3-char type)
        #    and 5-char proprietary (e.g. PASHR, PGRMF)
        if len(prefix) == 5:
            stype = prefix[2:]
            if stype in _STD_TIME:
                return self._extract_standard(stype, fields)
            if prefix in _PROP5_TIME:
                return self._extract_prop5(prefix, fields)

        # 2. Sub-typed proprietary (prefix + first data field)
        if len(fields) > 1:
            sub = _strip_checksum(fields[1]).strip().upper()
            subkey = (prefix, sub)
            if subkey == ('PSXN', '26'):
                return self._extract_psxn26(fields)
            if subkey in _SUB_TIME:
                return self._extract_subtype(subkey, fields)

        # 3. Long-name proprietary (>5 chars)
        if prefix in _LONG_TIME:
            return self._extract_long(prefix, fields)

        return None

    # -- Extraction helpers ------------------------------------------------

    def _extract_standard(self, stype, fields):
        """Extract datetime from a standard NMEA sentence."""
        time_idx = _STD_TIME[stype]
        date = None
        if stype == 'ZDA':
            day_i, month_i, year_i = _ZDA_DATE_FIELDS
            date = self._parse_zda_date(
                self._get_field(fields, day_i),
                self._get_field(fields, month_i),
                self._get_field(fields, year_i))
        elif stype in _STD_DATE:
            date = self._parse_ddmmyy(
                self._get_field(fields, _STD_DATE[stype]))
        return self._datetime_from_time_field(
            self._get_field(fields, time_idx), date=date)

    def _extract_prop5(self, prefix, fields):
        """Extract datetime from a 5-char proprietary sentence."""
        time_idx = _PROP5_TIME[prefix]
        date = None
        if prefix in _PROP5_DATE:
            date = self._parse_ddmmyy(
                self._get_field(fields, _PROP5_DATE[prefix]))
        return self._datetime_from_time_field(
            self._get_field(fields, time_idx), date=date)

    def _extract_subtype(self, subkey, fields):
        """Extract datetime from a sub-typed proprietary sentence."""
        time_idx = _SUB_TIME[subkey]
        date = None
        if subkey in _SUB_DATE:
            date = self._parse_ddmmyy(
                self._get_field(fields, _SUB_DATE[subkey]))
        return self._datetime_from_time_field(
            self._get_field(fields, time_idx), date=date)

    def _extract_long(self, prefix, fields):
        """Extract datetime from a long-name proprietary sentence."""
        time_idx = _LONG_TIME[prefix]
        return self._datetime_from_time_field(
            self._get_field(fields, time_idx))

    def _extract_psxn26(self, fields):
        """Extract datetime from PSXN,26 (separate Y/M/D/H/M/S fields)."""
        try:
            year = int(self._get_field(fields, 2))
            month = int(self._get_field(fields, 3))
            day = int(self._get_field(fields, 4))
            hour = int(self._get_field(fields, 5))
            minute = int(self._get_field(fields, 6))
            sec_str = self._get_field(fields, 7)
            second_frac = float(sec_str)
            second = int(second_frac)
            microsecond = int((second_frac - second) * 1_000_000)
            date = datetime(year, month, day, tzinfo=timezone.utc).date()
            self.last_nmea_date = date
            return datetime(
                year=year, month=month, day=day,
                hour=hour, minute=minute, second=second,
                microsecond=microsecond, tzinfo=timezone.utc)
        except (ValueError, IndexError):
            return None

    # -- Field access and parsing ------------------------------------------

    @staticmethod
    def _get_field(fields, idx):
        """Safely get a comma-split field, stripping any checksum suffix."""
        if idx < len(fields):
            return _strip_checksum(fields[idx].strip())
        return ''

    def _datetime_from_time_field(self, time_field, date=None):
        """Parse an NMEA time field (hhmmss.ss) and combine with a date.
        If *date* is provided, also update ``self.last_nmea_date``.
        """
        m = NMEA_TIME_RE.match(time_field)
        if not m:
            return None

        hour = int(m.group(1))
        minute = int(m.group(2))
        second_frac = float(m.group(3))
        second = int(second_frac)
        microsecond = int((second_frac - second) * 1_000_000)

        if date is not None:
            self.last_nmea_date = date
        use_date = self.last_nmea_date
        if use_date is None:
            use_date = datetime.now(timezone.utc).date()

        return datetime(
            year=use_date.year, month=use_date.month, day=use_date.day,
            hour=hour, minute=minute, second=second,
            microsecond=microsecond, tzinfo=timezone.utc,
        )

    @staticmethod
    def _parse_ddmmyy(date_field):
        """Parse a ``ddmmyy`` date string (used by RMC, PGRMF, etc.)."""
        if not date_field or len(date_field) < 6:
            return None
        try:
            day = int(date_field[0:2])
            month = int(date_field[2:4])
            year = int(date_field[4:6])
            year += 2000 if year < 80 else 1900
            return datetime(year, month, day, tzinfo=timezone.utc).date()
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _parse_zda_date(day_field, month_field, year_field):
        """Parse day, month, year fields from a ZDA sentence."""
        try:
            day = int(day_field)
            month = int(month_field)
            year = int(year_field)
            return datetime(year, month, day, tzinfo=timezone.utc).date()
        except (ValueError, IndexError):
            return None
