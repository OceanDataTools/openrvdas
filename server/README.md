# OpenRVDAS Servers

## Overview

Please see the [README.md file in the parent directory](../README.md)
for an introduction to the OpenRVDAS system. This document discusses
servers designed to manage, run, monitor and serve data from OpenRVDAS
loggers, either locally or on other machines via client connections.

## Installation

If you have already installed the files needed to run the core
OpenRVDAS code, as described in [the parent directory
INSTALL.md](../INSTALL.md); you will need to install some additional
Python modules to have full use of OpenRVDAS modules:

```
  pip3 install websockets parse PyYAML
```
If the LoggerManager code is to serve data via display widgets, you'll
also need to install the necessary database components by following
instructions in the [database/README.md file](../database/README.md).

## Running

This section describes running the OpenRVDAS servers: the LoggerRunner
and LoggerManager.

### LoggerRunner - Standalone

The LoggerRunner takes a dictionary of logger configurations and tries
to start and keep the specified loggers running. It can be invoked
from the command line as:

```
    server/logger_runner.py --config test/configs/sample_configs.yaml
```

*Note*: The sample_configs.yaml file above specifies configs that read
from simulated serial ports and write to UDP port 6224. To get the
configs to actually run, you'll need to run
```
  python3 logger/utils/simulate_serial.py \
    --config test/NBP1406/serial_sim_NBP1406.yaml \
    --loop 
```
in a separate terminal window to create the virtual serial ports the
sample config references and feed simulated data through them.)

To verify that the scripts are actually working as intended, you can
create a network listener on port 6224 in yet another window:

```
    logger/listener/listen.py --network :6224 --write_file -
```

### LoggerManager

To run the LoggerManager from the command line with (using the default
of an InMemoryServerAPI):

```
    server/logger_manager.py
```

If an initial configuration is specified on the command line, as
below:

```
    server/logger_manager.py --config test/NBP1406/NBP1406_cruise.yaml
```
the cruise configuration will be loaded and set to its default
mode. If a ``--mode`` argument is included, it will be used in place of
the default mode.

The ``-v`` flag may be specified on any of the above command lines to
increase diagnostic verbosity to "INFO". Repeating the flag sets
verbosity to "DEBUG".

For the LoggerManager and LoggerRunner, the ``-V`` (capitalized) flag
increases verbosity of the loggers being run.

### Running the Scripts Together
To try out the scripts, open three terminal windows.

1. In the first terminal, start the LoggerManager with a data server
(officially a CachedDataServer):
```
  server/logger_manager.py \
    --config test/NBP1406/NBP1406_cruise.yaml \
    --start_data_server
``````

2. The sample cruise that we're going to load and run is configured to
   read from simulated serial ports. To create those simulated ports
   and start feeding data to them, use a third terminal window to run:

```
  logger/utils/simulate_serial.py \
    --config test/NBP1406/serial_sim_NBP1406.yaml \
    --loop 
```

3. Finally, we'd like to be able to easily glimpse the data that the
   loggers are producing. The sample cruise configuration tells the
   loggers to write data to UDP port 6225 when running, so use the
   third terminal to run a Listener that will monitor that port. The '-'
   filename tells the Listener to write to stdout (see listen.py
   --help for all Listener options):

```
    logger/listener/listen.py --network :6225 --write_file -
```

4. Whew! Now try a few commands in the terminal running the
   LoggerManager (you can type 'help' for a full list):

#### Load a cruise configuration
```
   command? load_configuration test/NBP1406/NBP1406_cruise.yaml
```
#### Change cruise modes
```
   command? get_modes
     Modes: off, monitor, log

   command? set_active_mode monitor
     (You should notice data appearing in the Listener window.)

   command? set_active_mode log
     (You should notice more data appearing in the Listener window, and
      the LoggerRunner in the second window should leap into action.)

   command? set_active_mode off
```

#### Manually change logger configurations
```
   command? get_loggers
     Loggers: knud, gyr1, mwx1, s330, eng1, rtmp

   command? get_logger_configs s330
     Configs for s330: s330->off, s330->net, s330->file/net/db
   
   command? set_active_logger_config s330 s330->net

   command? set_active_mode off

   command? quit
```
When setting the mode to monitor, you should notice data appearing in
the listener window, and should see diagnostic output in the
LoggerManager window.

## Server API

The LoggerManager stores and retrieves configuration and status data
using a backing store. There are currently three backing stores
implemented: an in-memory based (``--database memory``), Django-based
(``--database django``) and a HAPI-based one (``--database hapi``).

By default, a LoggerManager will use the in-memory backing store. This
means that state will be lost whenever the LoggerManager is
restarted. If you have Django installed or a HAPI-based server
running, you may run using those options to maintain persistence.

The backing stores are implemented via an API; for details on the
API and its implementations, please see
[server/server\_api.py](../server/server\_api.py),
[server/in\_memory\_server\_api.py](../server/in\_memory\_server\_api.py),
and
[django\_gui/django\_server\_api.py](../django\_gui/django\_server\_api.py).

## Contributing

Please contact David Pablo Cohn (*david dot cohn at gmail dot com*) -
to discuss opportunities for participating in code development.

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

