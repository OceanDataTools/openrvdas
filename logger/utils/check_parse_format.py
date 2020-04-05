#!/usr/bin/env python3
"""Check whether a PyPi parse string format matches a given string. If
not, show at what point the match fails.

  > logger/utils/check_parse_format.py \
      --format '$GPGLL,{Latitude:nlat},{NorS:w},{Longitude:nlat},{EorW:w}' \
      --string '$GPGLL,2203.672,S,01759.539,W'

  Matches!

  > logger/utils/check_parse_format.py \
      --format '$GPGLL,{Latitude:nlat},{NorS:w},{Longitude:nlat},{EorW:w}' \
      --string '$GPGLL,2203.672,S,01759.5x39,W'

  Matches up to $GPGLL,{Latitude:nlat},{NorS:w},{Longitude:nlat}
  $GPGLL,2203.672,S,01759.5x39,W
  _________________________^

***NOTE***: When used from the command line, unless you use single (not
double) quotes on your strings, any "$" character will be interpreted
as the start of a shell variable and may muck up your match.

"""
import logging
import os.path
import parse
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

from logger.utils.record_parser import RecordParser

# Dict of format types that extend the default formats recognized by the
# parse module.
from logger.utils.record_parser_formats import extra_format_types

# We add an "anything" type to eat up stuff at the end of a string
def anything(text):
  """Method for parsing a string (or anything) between commas
  string."""
  if text:
    return text
  else:
    return None
anything.pattern = r'.*'

extra_format_types['anything'] = anything

################################################################################
def check_parse_format(format, string):
  """Check whether a format pattern matches a string. Return None if
  there is a complete match, or a tuple of

    (index_of_max_match, substring of pattern that matches)

  if the match fails.
  """

  # First check: do we match the entire string? If so, we're done -
  # return None.
  if parse.parse(format, string, extra_types=extra_format_types):
    return None

  # If we haven't matched, try matching shorter and shorter patterns,
  # followed by anything.
  max_index = len(format)
  while max_index > 0:
    new_format = format[0:max_index] + '{Anything:anything}'
    try:
      p = None
      p = parse.parse(new_format, string, extra_types=extra_format_types)
    except ValueError: # Probably got an incomplete pattern. Keep chopping.
      pass

    if p:
      del p.spans['Anything']
      max_span = max([v[1] for k,v in p.spans.items()])
      return (max_span, format[0:max_index])

    # If didn't match, shorten the format
    #print('Didn\'t match "{}"'.format(format[0:max_index]))
    max_index -= 1


################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()

  parser.add_argument('--format', dest='format', help='PyPi format string')
  parser.add_argument('--string', dest='string', help='String to match')
  args = parser.parse_args()

  result = check_parse_format(args.format, args.string)
  if result is None:
    print('Matches!')
  else:
    max_span, format = result
    print('Matches up to {}'.format(format))
    print(args.string)
    print('_' * max_span + '^')
