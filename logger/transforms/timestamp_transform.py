#!/usr/bin/env python3

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import timestamp  # noqa: E402
from logger.utils.nmea_timestamp import NMEATimestampExtractor  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class TimestampTransform(Transform):
    """Prepend a timestamp to a text record.

    By default the system clock is used.  When ``use_nmea_timestamp`` is
    enabled, the transform first attempts to extract the timestamp
    embedded in NMEA 0183 sentences (GGA, RMC, ZDA, and many others)
    and only falls back to the system clock when no NMEA time is
    available.

    Parameters
    ----------
    time_format : str
        strftime format string for the prepended timestamp.  Defaults
        to ``logger.utils.timestamp.TIME_FORMAT``
        (``'%Y-%m-%dT%H:%M:%S.%fZ'``).
    time_zone : datetime.timezone
        Timezone applied to the timestamp.  Defaults to UTC.
    sep : str
        Separator inserted between the timestamp and the record text.
        Defaults to a single space.

    use_nmea_timestamp : bool
        When True, attempt to parse the NMEA time field from the
        incoming record before falling back to the system clock.
        Defaults to False.
    nmea_timestamp_timeout : float
        How many seconds a previously-extracted NMEA timestamp remains
        valid for records that do not carry their own time field
        (e.g. VTG, HDT).  After this period the system clock is used
        instead.  Defaults to 1 s.
    nmea_time_drift_threshold : float or None
        If the absolute difference between the NMEA-derived time and
        the system clock exceeds this value (in seconds), a warning is
        logged.  Set to None to disable the check.  Defaults to 0.1 s.
    quiet : bool
        Inherited from Transform (passed via ``**kwargs``).  When True,
        suppresses all warnings from both the transform and the
        underlying NMEATimestampExtractor (drift, staleness, and
        fallback warnings).  Defaults to False.
    """
    def __init__(self, time_format=timestamp.TIME_FORMAT,
                 time_zone=timestamp.timezone.utc, sep=' ',
                 use_nmea_timestamp=False,
                 nmea_timestamp_timeout=1,
                 nmea_time_drift_threshold=0.1, **kwargs):
        """Create a TimestampTransform."""
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        self.time_format = time_format
        self.time_zone = time_zone
        self.sep = sep
        self.use_nmea_timestamp = use_nmea_timestamp
        self.nmea_extractor = None
        if use_nmea_timestamp:
            self.nmea_extractor = NMEATimestampExtractor(
                timeout=nmea_timestamp_timeout,
                quiet=self.quiet,
                time_drift_threshold=nmea_time_drift_threshold)

    ############################
    def transform(self, record: str, ts=None) -> str:
        """Prepend a timestamp"""

        # If they've not given us a timestamp, find one.
        if ts is None:
            if self.nmea_extractor is None:
                # Things are simple if we're not trying to extract a timestamp from NMEA.
                ts = timestamp.time_str(time_format=self.time_format,
                                        time_zone=self.time_zone)
            else:
                # If we're going to try to extract ts from NMEA
                ts = self.nmea_extractor.get_timestamp(
                    record, self.time_format, self.time_zone)
                # Failed, so fall back to system time.
                if ts is None and not self.quiet:
                    logging.warning(
                        'TimestampTransform: no NMEA timestamp for record, '
                        'falling back to system time')
                ts = ts or timestamp.time_str(time_format=self.time_format,
                                              time_zone=self.time_zone)

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            # Special case: if we can't process it, but it's a list, pass
            # along the same initial timestamp so all elements in the list
            # share the same timestamp.
            if isinstance(record, list):
                return [self.transform(r, ts) for r in record]
            # If not str and not list, pass it along to digest_record()
            # to let it try and/or complain.
            else:
                return self.digest_record(record)  # inherited from BaseModule()

        # If it is something we can process, put a timestamp on it.
        return ts + self.sep + record
