#!/usr/bin/env python3

"""Custom format definitions for RecordParser.

To use, import the 'extra_format_types' dict and pass to the parser:

import parse
from logger.utils.record_parser_formats import extra_format_types

pattern = parse.compile(format=record_format, extra_types=extra_format_types)
parsed_values = pattern.parse(record)

# Why We Have This

We want to expand the default repertoire of the parse() function to be
able to handle ints/floats/strings that *might* be omitted. To do
that, we define some additional named types for it that we can use in
format definitions.

These might be used, for example, in the following pattern where we
might have either, both or neither of speed in knots and/or km/hour.

  "{SpeedKt:of},N,{SpeedKm:of},K"

The recognized format types we add are:
  od   = optional integer
  of   = optional generalized float
  og   = optional generalized number - also handles '#VALUE!' as None
  ow   = optional sequence of letters, numbers, underscores
  os   = optional sequence of any characters - will match everything on line

  nlat = NMEA-formatted latitude or longitude, converted to decimal degrees

  nc = any ASCII text that is not a comma
  ns = any ASCII text that is not an asterisk ("star")

See 'Custom Type Conversions' in https://pypi.org/project/parse/ for a
discussion of how format types work.

TODO: allow device_type definitions to hand in their own format types.
"""
import logging


def optional_d(text):
    """Method for parsing an 'optional' integer."""
    if text:
        return int(text)
    else:
        return None


optional_d.pattern = r'\s*[-+]?\d*'


def optional_f(text):
    """Method for parsing an 'optional' generalized float."""
    if text:
        return float(text)
    else:
        return None


optional_f.pattern = r'(\s*[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?|)'


def optional_g(text):
    """Method for parsing an 'optional' generalized number."""
    if text == '#VALUE!':
        return None
    if text:
        return float(text)
    else:
        return None


optional_g.pattern = r'(#VALUE!|\s*[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?|\d*)'


def optional_w(text):
    """Method for parsing an 'optional' letters/numbers/underscore
    string."""
    if text:
        return text
    else:
        return None


optional_w.pattern = r'\w*'


def optional_s(text):
    """Method for parsing any sequence of zero or more characters. Will absorb
    everything in the string.
    """
    if text:
        return text
    else:
        return ''


optional_s.pattern = r'.*'


def nmea_lat_lon(text):
    """Method for parsing an NMEA latitude or longitude (DDDMM.MMMM) and
    converting it into decimal degrees. Only handles the numeric part, not
    any E/W or N/S component."""
    if text:
        nmea_value = float(text)
        normalized_value = nmea_value / 100
        degrees = int(normalized_value)
        if abs(degrees) >= 180.0:
            logging.warning('Improper NMEA-style latitude/longitude: "%s"', text)
            return None
        fractional_degrees = (normalized_value - degrees) / 0.60
        if abs(fractional_degrees) >= 1.0:
            logging.warning('Improper NMEA-style latitude/longitude: "%s"', text)
            return None
        return degrees + fractional_degrees
    else:
        return None


nmea_lat_lon.pattern = r'(\s*[-]?(\d+(\.\d*)?|\.\d+)?|)'


def nmea_lat_lon_dir(text):
    """Method for parsing an NMEA latitude or longitude (DDDMM.MMMM) along
    with the hemisphere (E/W/N/S) and converting it into signed decimal
    degrees. South and West are considered negative, North and East
    positive.
    """
    if text:
        nmea_str, dir = text.split(',')
        nmea_value = float(nmea_str)
        normalized_value = nmea_value / 100
        degrees = int(normalized_value)
        if abs(degrees) >= 180.0:
            logging.warning('Improper NMEA-style latitude/longitude: "%s"', text)
            return None
        fractional_degrees = (normalized_value - degrees) / 0.60
        if abs(fractional_degrees) >= 1.0:
            logging.warning('Improper NMEA-style latitude/longitude: "%s"', text)
            return None
        decimal_degrees = degrees + fractional_degrees
        if dir in ['W', 'S']:
            decimal_degrees = -decimal_degrees
        return decimal_degrees
    else:
        return None


nmea_lat_lon_dir.pattern = r'(\s*(\d+(\.\d*)?|\.\d+),[NEWS]?|)'


def not_comma(text):
    """Method for parsing a string (or anything) between commas
    string."""
    if text:
        return text
    else:
        return None


not_comma.pattern = r'[^,]*'


def not_star(text):
    """Method for parsing a string (or anything) terminated by a "*"
    """
    if text:
        return text
    else:
        return None


not_star.pattern = r'[^\*]*'


extra_format_types = dict(
    od=optional_d,
    of=optional_f,
    og=optional_g,
    ow=optional_w,
    os=optional_s,

    nlat=nmea_lat_lon,
    nlat_dir=nmea_lat_lon_dir,

    nc=not_comma,
    ns=not_star)
