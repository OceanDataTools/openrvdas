# OpenRVDAS

##Synopsis

This project is a set of Python scripts implementing a data
acquisition system for research vessels and other scientific
installations. It allows reading data records (from serial ports and
network-aware sensors), then processing and storing those records

The code is designed to be modular and extensible, relying on simple
composition of Readers, Transforms and Writers to achieve the needed
functionality. Individual modules can be composed using a few lines of
Python, e.g.

    reader = SerialReader(port='/dev/ttyr15', baudrate=9600)
    timestamp_transform = TimestampTransform()
    prefix_transform = PrefixTransform(prefix=‘knud’)
    logfilewriter = LogfileWriter(filebase=‘/data/logs/current/knud’)
    while True:
      in_record = reader.read()
      ts_record = timestamp_transform.transform(in_record)
      out_record = prefix_transform.transform(ts_record)
      writer.write_record(out_record)

In addition, a simple listen.py script provides access to the most
commonly used Readers, Transforms and Writers from the command line,
e.g.

listen.py --serial port=/dev/ttyr15,baudrate=9600 \
    --timestamp --prefix knud \
    --write_logfile /data/logs/current/knud

##Code Example

See synopsis above, and run

  logger/listener/listen.py --help

for full help on the listener script.

##Motivation

One of the primary values a research vessel offers is the opportunity
to gather accurate and timely scientific data wherever it
travels. Most ships carry some combination of oceanographic,
meteorological and other sensors and operate a system for storing,
processing, analyzing and displaying the data they produce.

At present there are limited options for a ship wishing to operate
such a system, and most either rely on a closed-source Windows-based
solution (SCS) or on custom-crafted versions of software dating from
the 1990's (dsLog, LDS). This limited choice means that expertise is
wasted in maintaining fragmented code, or stifled while waiting for a
monolithic system to implement feature requests.

Every ship will have different requirements, so no single system can
hope to accommodate everyone's needs. In addition, those requirements
will change from mission to mission and year to year, so no fixed
system will be optimal for any length of time.

Because of this, instead of a system, we have focused on designing and
building an architecture that allows easy assembly of small, modular
components into whatever system is needed in a given situation.

##Installation

Note that the code itself is still very much under development. The
core logging functionality only relies on Python 3 (tested on Python
3.5 and above). You should be able to simply unpack the distribution
and run

  logging/listener/listen.py --help

from the project's home directory.


##API Reference

Documentation (also still incomplete) for the code is available online
in a shared Google Doc folder via the shortcut url
http://tinyurl.com/openrvdas-docs.

##Tests

Full unit tests for the code base may be run from the project home
directory by running

    python3 -m unittest discover

Tests may be run on a directory by directory basis with

    python3 -m unittest discover logger.readers

for example, to test all code in logger/readers.

Specific unit tests may be run individually, as well:

    logger/readers/test_network_reader.py -v -v

Many (but not yet all) accept -v flags to increase the verbosity of
the test: a single '-v' sets logging level to "info"; a second -v sets
it to "debug".

##Contributors

Please contact David Pablo Cohn <david.cohn@gmail.com> - to discuss
opportunities for participating in code development.

##License

This code is made available under the MIT license:

Copyright (c) 2017 David Pablo Cohn

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

##Additional Licenses
