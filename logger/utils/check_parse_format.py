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
import parse
import pprint

# Dict of format types that extend the default formats recognized by the
# parse module.
from logger.utils.record_parser_formats import extra_format_types  # noqa: E402

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
    """Check whether a format pattern matches a string. If there is a
    complete match, return

      (match_dict, None, None)

    If there is a partial match, return

      (match_dict, index_of_max_match, substring of pattern that matches)

    If there is no match, return

      (None, None, None)
    """

    # First check: do we match the entire string? If so, we're done -
    # return None.
    p = parse.parse(format, string, extra_types=extra_format_types)
    if p:
        return (p.named, None, None)

    # If we haven't matched, try matching shorter and shorter patterns,
    # followed by anything.
    max_index = len(format)
    while max_index > 0:
        new_format = format[0:max_index] + '{Anything:anything}'
        try:
            p = parse.parse(new_format, string, extra_types=extra_format_types)
        except ValueError:  # Probably got an incomplete pattern. Keep chopping.
            p = None

        if p:
            del p.spans['Anything']
            del p.named['Anything']
            span_ends = [v[1] for k, v in p.spans.items()] or [0]
            max_span = max(span_ends)
            return (p.named, max_span, format[0:max_index])

        # If didn't match, shorten the format
        # print('Didn\'t match "{}"'.format(format[0:max_index]))
        max_index -= 1

    # Nothing ever matched
    return (None, None, None)


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument('--format', dest='format', help='PyPi format string')
    parser.add_argument('--string', dest='string', help='String to match')
    args = parser.parse_args()

    match_dict, max_span, format = check_parse_format(args.format, args.string)
    print('')
    if match_dict is None:
        print('No match at all!')
    elif max_span is None:
        print('Matches: %s' % pprint.pformat(match_dict))
    else:
        print('Partial match up to "{}"'.format(format))
        print(args.string)
        print('_' * max_span + '^')
        print('Values: %s' % pprint.pformat(match_dict))
