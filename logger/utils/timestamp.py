#!/usr/bin/env python3

"""Tools for generating numeric timestamps, converting from timestamps
into strings and parsing time strings into numeric timestamps.

Use UTC as default timezone.

timestamp(time_str=None, time_zone=timezone.utc, time_format=TIME_FORMAT)

  Return numeric timestamp for a passed time_str. If no time_str is
  passed, return timestamp for now.

time_str(timestamp=None, time_zone=timezone.utc, time_format=TIME_FORMAT)

  Given a timestamp, return a string representing that time. If no
  timestamp is given, return the string for now.

date_str(timestamp=None, time_zone=timezone.utc, time_format=TIME_FORMAT)

  Given a timestamp, return a string representing the date of that
  time. If no timestamp is given, return the string for today.

TODO: read date/time format from some central settings file.

"""
from datetime import datetime, timezone

TIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'  # ISO 8601
LOGGING_TIME_FORMAT = '%Y-%m-%dT%H:%M:%S'  # ISO 8601

DATE_FORMAT = '%Y-%m-%d'              # ISO 8601

# As used on the NBP
# DATE_FORMAT = '%y+%j'      # Julian
# TIME_FORMAT = '%y+%j:%H:%M:%S.%f'  # Julian

# DATE_FORMAT = '%Y-%m-%d'    # Gregorian
# TIME_FORMAT = '%Y-%m-%d:%H:%M:%S.%f'  # Gregorian

################################################################################


def datetime_obj(time_str=None, time_zone=timezone.utc, time_format=TIME_FORMAT):
    """Return datetime object for a passed time_str. If no time_str is
    passed, return datetime object for now."""
    if time_str is None:
        return datetime.now(time_zone)

    # If they've given us a time string to convert. Set timezone as necessary.
    return datetime.strptime(time_str, time_format).replace(tzinfo=time_zone)

################################################################################


def datetime_obj_from_timestamp(timestamp, time_zone=timezone.utc):
    """Return datetime object for a passed timestamp."""

    # If they've given us a time string to convert. Set timezone as necessary.
    return datetime.fromtimestamp(timestamp, tz=time_zone)

################################################################################


def timestamp(time_str=None, time_zone=timezone.utc, time_format=TIME_FORMAT):
    """Return numeric timestamp for a passed time_str. If no time_str is
    passed, return timestamp for now."""
    return datetime_obj(time_str, time_zone, time_format).timestamp()

################################################################################


def time_str(timestamp=None, time_zone=timezone.utc, time_format=TIME_FORMAT):
    """Given a timestamp, return a string representing that time. If no
    timestamp is given, return the string for now."""
    if timestamp is None:
        timestamp = datetime.now(time_zone).timestamp()
    return datetime.fromtimestamp(timestamp, time_zone).strftime(time_format)

################################################################################


def date_str(timestamp=None, time_zone=timezone.utc, date_format=DATE_FORMAT):
    """Given a timestamp, return a string representing that date. If no
    timestamp is given, return the string for today."""
    return time_str(timestamp, time_zone, date_format)
