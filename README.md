# OpenRVDAS

## Overview

Open Research Vessel Data Acquisition System (OpenRVDAS) is a 
software framework used for building custom data acquisition 
systems (DAS).  OpenRVDAS target audiences are oceanographic 
research vessels operators and other operators of other science-
related platforms that have the need to record streaming data. 
OpenRVDAS is capable of reading data records from serial ports and 
network-aware sensors, optionally modifying those data records and 
streaming either the original or modified version of the data 
stream to a destination such as afile, network port, database, etc.

OpenRVDAS is designed to be modular and extensible, relying on simple
composition of Readers, Transforms and Writers to achieve the needed
datalogging functionality.

## Motivation

The primary purpose of an oceanographic research vessel is to gather
data from sensors. Oceanographic research vessels carry a combination 
of oceanographic, meteorological and other specialized sensors. Some 
of the more complex sensors (i.e. ADCP, Multibeam, imaging systems) 
include specialized DAS systems tailored to that particlular sensor 
system.  The rest of the more simplistic sensors will stream data 
values over a network port or serial connection.

At present there are limited options for oceanographic research 
vessel operators requiring a tool to record data from simplistic 
streaming sensors. This task is commonly referred to as underway data
logging.  Most research vessel operators rely on closed-source, 
solutions (i.e. SCS, WinFrog) or on dated datalogging systems (i.e. 
dsLog, LDS) for underway data logging.  Both options provide limited 
support mechanisms, thus bugs are slow to be resolved and feature 
requests are slow to be implemented.

OpenRVDAS hopes to provide an alternative underway data logging 
solution that is defined, developed and maintained by the global
oceanographic research community.

OpenRVDAS recognizes that each ship is different, that each ship has a
unique set of sensors and that each ship has a unique way of operating.  
With this understanding, OpenRVDAS does not try provide a turn-key, one-
size-fits-all solution but instead provides research vessel operators 
with a modular and extendable toolset for developing and deploying a custom
underway datalogging solution tailored to the vessel's individual needs.

DISCLAIMER: THIS CODE IS EXPERIMENTAL AND STILL IN THE *VERY* EARLY
STAGES OF DEVELOPMENT. IT SHOULD UNDER NO CIRCUMSTANCES BE RELIED ON,
ESPECIALLY NOT IN ANY APPLICATION WHERE ITS FAILURE COULD RESULT IN
INJURY, LOSS OF LIFE, PROPERTY, SANITY OR CREDIBILITY AMONG YOUR PEERS
WHO WILL TELL YOU THAT YOU REALLY SHOULD HAVE KNOWN BETTER.

## Installation

Please refer to [INSTALL.md]<INSTALL.md> for details on how to install OpenRVDAS

## Data logging

### Writing a custom logging script
Individual logging modules can be composed using a few lines of
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

#### Full API Reference
Documentation (also still incomplete) for the code is available online
in a shared Google Doc folder via the shortcut url
<http://tinyurl.com/openrvdas-docs>.

### Logging with listen.py
The listen.py script is included to provide access to the most
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

## Contributing

Please contact David Pablo Cohn (*david dot cohn at gmail dot com*) - to discuss
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
