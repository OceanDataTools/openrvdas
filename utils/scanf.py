"""
Small scanf implementation.

Python has powerful regular expressions but sometimes they are totally overkill
when you just want to parse a simple-formatted string.
C programmers use the scanf-function for these tasks (see link below).

This implementation of scanf translates the simple scanf-format into
regular expressions. Unlike C you can be sure that there are no buffer overflows
possible.

For more information see
  * http://www.python.org/doc/current/lib/node49.html
  * http://en.wikipedia.org/wiki/Scanf

Original code from:
	http://code.activestate.com/recipes/502213-simple-scanf-implementation/

Modified original to make the %f more robust, as well as added %* modifier to
skip fields.

===============

The MIT License (MIT)

Copyright (c) 2016 joshburnett

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"""
import re
import sys

__version__ = '1.4.1'

__all__ = ["scanf", 'extractdata', 'scanf_translate', 'scanf_compile']


DEBUG = False



# As you can probably see it is relatively easy to add more format types.
# Make sure you add a second entry for each new item that adds the extra
#   few characters needed to handle the field ommision.
scanf_translate = [
    (re.compile(_token), _pattern, _cast) for _token, _pattern, _cast in [
    ("%c", "(.)", lambda x:x),
    ("%\*c", "(?:.)", None),

    ("%(\d)c", "(.{%s})", lambda x:x),
    ("%\*(\d)c", "(?:.{%s})", None),

    ("%(\d)[di]", "([+-]?\d{%s})", int),
    ("%\*(\d)[di]", "(?:[+-]?\d{%s})", None),

    ("%[di]", "([+-]?\d+)", int),
    ("%\*[di]", "(?:[+-]?\d+)", None),

    ("%u", "(\d+)", int),
    ("%\*u", "(?:\d+)", None),

    ("%[fgeE]", "([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)", float),
    ("%\*[fgeE]", "(?:[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)", None),

    ("%s", "(\S+)", lambda x:x),
    ("%\*s", "(?:\S+)", None),

    ("%([xX])", "(0%s[\dA-Za-f]+)", lambda x:int(x, 16)),
    ("%\*([xX])", "(?:0%s[\dA-Za-f]+)", None),

    ("%o", "(0[0-7]*)", lambda x:int(x, 8)),
    ("%\*o", "(?:0[0-7]*)", None),
    ]]



# Cache formats
SCANF_CACHE_SIZE = 1000
scanf_cache = {}


def scanf_compile(format, collapseWhitespace=True):
    """
    Translate the format into a regular expression

    For example:
    >>> format_re, casts = _scanf_compile('%s - %d errors, %d warnings')
    >>> print format_re.pattern
    (\S+) \- ([+-]?\d+) errors, ([+-]?\d+) warnings

    Translated formats are cached for faster reuse
    """
    compiled = scanf_cache.get(format)
    if compiled:
        return compiled

    format_pat = ""
    cast_list = []
    i = 0
    length = len(format)
    while i < length:
        found = None
        for token, pattern, cast in scanf_translate:
            found = token.match(format, i)
            if found:
                if cast: # cast != None
                    cast_list.append(cast)
                groups = found.groupdict() or found.groups()
                if groups:
                    pattern = pattern % groups
                format_pat += pattern
                i = found.end()
                break
        if not found:
            char = format[i]
            # escape special characters
            if char in "|^$()[]-.+*?{}<>\\":
                format_pat += "\\"
            format_pat += char
            i += 1
    if DEBUG:
        print("DEBUG: %r -> %s" % (format, format_pat))
    if collapseWhitespace:
        format_pat = re.sub('\s+',r'\s+',format_pat)

    format_re = re.compile(format_pat)
    if len(scanf_cache) > SCANF_CACHE_SIZE:
        scanf_cache.clear()
    scanf_cache[format] = (format_re, cast_list)
    return format_re, cast_list



def scanf(format, s=None, collapseWhitespace=True):
    """
    scanf supports the following formats:
      %c        One character
      %5c       5 characters
      %d, %i    int value
      %7d, %7i  int value with length 7
      %f        float value
      %o        octal value
      %X, %x    hex value
      %s        string terminated by whitespace

    Examples:
    >>> scanf("%s - %d errors, %d warnings", "/usr/sbin/sendmail - 0 errors, 4 warnings")
    ('/usr/sbin/sendmail', 0, 4)
    >>> scanf("%o %x %d", "0123 0x123 123")
    (66, 291, 123)


    scanf.scanf returns a tuple of found values
    or None if the format does not match.
    """

    if s == None: s = sys.stdin
    if hasattr(s, "readline"): s = s.readline()

    format_re, casts = scanf_compile(format, collapseWhitespace)

    found = format_re.search(s)
    if found:
        groups = found.groups()
        return tuple([casts[i](groups[i]) for i in range(len(groups))])



def extractdata(pattern, text=None, filepath=None):
    """
    Read through an entire file or body of text one line at a time. Parse each line that matches the supplied pattern string and ignore the rest.

    If *text* is supplied, it will be parsed according to the *pattern* string.
    If *text* is not supplied, the file at *filepath* will be opened and parsed.
    """
    y = []
    if text is None:
        textsource = open(filepath, 'r')
    else:
        textsource = text.splitlines()

    for line in textsource:
        match = scanf(pattern, line)
        if match:
            if len(y) == 0:
                y = [[s] for s in match]
            else:
                for i,ydata in enumerate(y):
                    ydata.append(match[i])

    if text is None:
        textsource.close()

    return y



if __name__ == "__main__":
    import doctest
    doctest.testmod(verbose=True, report=True)
