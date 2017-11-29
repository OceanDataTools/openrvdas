# OpenRVDAS

## Synopsis

This project is a set of Python scripts implementing a data
acquisition system (DAS) for research vessels and other scientific
installations. It allows for reading data records (from serial ports 
and network-aware sensors), processing those data records and 
streaming the original records or a modified version of the orignial 
record to a destination (file, network port, database, etc).

The code is designed to be modular and extensible, relying on simple
composition of Readers, Transforms and Writers to achieve the needed
functionality. Individual modules can be composed using a few lines of
Python, e.g.
```
    reader = SerialReader(port='/dev/ttyr15', baudrate=9600)
    timestamp_transform = TimestampTransform()
    prefix_transform = PrefixTransform(prefix=‘knud’)
    logfilewriter = LogfileWriter(filebase=‘/data/logs/current/knud’)
    while True:
      in_record = reader.read()
      ts_record = timestamp_transform.transform(in_record)
      out_record = prefix_transform.transform(ts_record)
      writer.write_record(out_record)
```

### listen.py
A simple listen.py script is included to provide access to the most
commonly used Readers, Transforms and Writers from the command line,
e.g.
```
  listen.py --serial port=/dev/ttyr15,baudrate=9600 \
      --timestamp --prefix knud \
      --write_logfile /data/logs/current/knud
```
#### More information on listen.py
For full details on the use of listen.py, run:
```
  logger/listener/listen.py --help
```

## Motivation

The primary purpose of an oceanographic research vessel is to gather
accurate and timely scientific data wherever it travels. 
Oceanographic research vessels carry a combination of oceanographic,
meteorological and other specialized sensors. Some of the more
complex sensors (i.e. ADCP, Multibeam, imaging systems) include 
specialized DAS systems tailored to that particlular sensor system.  
The rest of the more simplistic sensors will stream real-time values 
over a network port or serial connection.

At present there are limited options for research vessel operators
requiring the means to record data from the before mentioned
simplistic sensors.  This is commonly referred to as underway data
logging.  Most research vessel operators rely on closed-source, 
Windows-based solutions (i.e. SCS, WinFrog) or on dated Linux-
based systems (i.e. dsLog, LDS) for underway data logging.  Both 
options have limited support mechanisms, thus bugs are slow to 
be resolved and feature requests are slow to be implemented.

OpenRVDAS hopes to provide an alternative underway data logging 
solution that is defined, developed and maintained by the global
oceanographic research community

OpenRVDAS recongizes that each ship is different, that each ship has a 
unique set of sensors and a unique way of operating.  With this 
understanding, OpenRVDAS doesn't not provide a turn-key, one-size-fits-
all solution but instead provides research vessel operators with a 
modular and extendable toolset for developing and deploying a custom
underway datalogging solution tailored to the vessel's individual needs.

DISCLAIMER: THIS CODE IS EXPERIMENTAL AND STILL IN THE *VERY* EARLY
STAGES OF DEVELOPMENT. IT SHOULD UNDER NO CIRCUMSTANCES BE RELIED ON,
ESPECIALLY NOT IN ANY APPLICATION WHERE ITS FAILURE COULD RESULT IN
INJURY, LOSS OF LIFE, PROPERTY, SANITY OR CREDIBILITY AMONG YOUR PEERS
WHO WILL TELL YOU THAT YOU REALLY SHOULD HAVE KNOWN BETTER.

## Installation

Note that OpenRVDAS is still very much under development. The
core logging functionality only relies on Python 3 (tested on Python
3.5 and above). You should be able to simply unpack the distribution
and run*

```
  logging/listener/listen.py --help
```

from the project's home directory.

Serial port functionality will require the pyserial.py package, which
may be installed using pip3:

```
  pip3 install pyserial
```

To test the system using the simulate_serial.py utility, you will also
need the 'socat' command installed on your system. See the 'OpenRVDAS
Introduction to Loggers' document <http://tinyurl.com/openrvdas-docs>
for more information.

## API Reference

Documentation (also still incomplete) for the code is available online
in a shared Google Doc folder via the shortcut url
<http://tinyurl.com/openrvdas-docs>.

## Tests

Full unit tests for the code base may be run from the project home
directory by running
```
    python3 -m unittest discover
```
Tests may be run on a directory by directory basis with
```
    python3 -m unittest discover logger.readers
```
for example, to test all code in logger/readers.

Specific unit tests may be run individually, as well:
```
    logger/readers/test_network_reader.py -v -v
```
Many (but not yet all) accept -v flags to increase the verbosity of
the test: a single '-v' sets logging level to "info"; a second -v sets
it to "debug".

## Contributors

Please contact David Pablo Cohn <david.cohn@gmail.com> - to discuss
opportunities for participating in code development.

## License

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

## Additional Licenses
