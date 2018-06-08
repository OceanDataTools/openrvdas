# OpenRVDAS Servers

## Overview

Please see the [README.md file in the parent directory](../README.md)
for an introduction to the OpenRVDAS system. This document discusses
servers designed to manage, run, monitor and serve data from OpenRVDAS
loggers, either locally or on other machines via client connections.

## Installation

If you have already installed the files needed to run the core
OpenRVDAS code, as described in [the parent directory
INSTALL.md](../INSTALL.md); you only need to install the websockets
module if it is not part of your existing installation: to run the
servers:

```
  pip3 install websockets
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
    server/logger_runner.py --config test/configs/sample_configs.json
```

*Note*: The sample_configs.json file above specifies configs that read
from simulated serial ports and write to UDP port 6224. To get the
configs to actually run, you'll need to run
```
    logger/utils/serial_sim.py --config test/serial_sim.py
```
in a separate terminal window to create the virtual serial ports the
sample config references and feed simulated data through them.)

To verify that the scripts are actually working as intended, you can
create a network listener on port 6224 in yet another window:
```
    logger/listener/listen.py --network :6224 --write_file -
```

### LoggerRunner - As Client

A LoggerRunner may also be started as a client for a remote
LoggerManager. To do so, specify a host and port of a running
LoggerManager (described below) using the ```--websocket``` argument
and assign it a host id by which to identify itself using the
```--host_id``` argument:

```
    server/logger_manager.py --websocket localhost:8765 --host_id master.host
```

When the LoggerManager identifies a config to be run that includes
   a host_id restriction, e.g.
```
    "knud->net": {
       "host_id": "knud.host",
       "readers": ...
        ...
    }
```

it will attempt to dispatch that config to the LoggerRunner that has
identified itself with that host id. (Note: configs with no host
restriction will be run by the LoggerManager itself, and if a config
has a host restriction and no host by that name has connected, the
LoggerManager will issue a warning and not run the configuration.)

### LoggerManager - Standalone

To run the LoggerManager from the command line with (using the default
of an InMemoryServerAPI):
```
    server/logger_manager.py
```
If an initial cruise config is specified on the command line, as
below:
```
    server/logger_manager.py --config test/configs/sample_cruise.json
```
the cruise configuration will be loaded and set to its default
mode. If a --mode argument is included, it will be used in place of
the default mode.

### LoggerManager - As Server

If the LoggerManager is created with a websocket specification
(host:port), it will accept connections from LoggerRunners. It
expects the LoggerRunners to identify themselves with a host_id, and
will dispatch any configs listing that host_id to the appropriate
LoggerRunner. Configs that have no host_id specified will continue to
be dispatched to the local LoggerRunner; configs specifying a host_id
that doesn't match any connected LoggerRunner will not be run:
```
    server/logger_manager.py --websocket localhost:8765
```
A LoggerRunner that would connect to the above LoggerManager could be
launched via:
```
    server/logger_runner.py --websocket localhost:8765 \
        --host_id knud.host
```
The ```-v``` flag may be specified on any of the above command lines to
increase diagnostic verbosity to "INFO". Repeating the flag sets
verbosity to "DEBUG".

For the LoggerManager and LoggerRunner, the ```-V``` (capitalized) flag
increases verbosity of the loggers being run.

### Running the Scripts Together
To try out the scripts, open four(!) terminal windows.

1. In the first terminal, start the LoggerManager with a websocket server:
```
   server/logger_manager.py --websocket localhost:8765 -v
```
2. In a second terminal, start a LoggerRunner that will try to connect
   to the websocket on the LoggerManager you've started.
```
    server/logger_runner.py --websocket localhost:8765 \
         --host_id knud.host -v
```
   Note that this LoggerRunner is identifies its host as "knud.host";
   if you look at test/configs/sample_cruise.json, you'll notice that
   the configs for the "knud" logger have a host restriction of
   "knud.host", meaning that our LoggerManager should try to dispatch
   those configs to this LoggerRunner.

3. The sample cruise that we're going to load and run is configured to
   read from simulated serial ports. To create those simulated ports
   and start feeding data to them, use a third terminal window to run:
```
    logger/utils/simulate_serial.py --config test/serial_sim.json -v
```
4. Finally, we'd like to be able to easily glimpse the data that the
   loggers are producing. The sample cruise configuration tells the
   loggers to write to UDP port 6224 when running, so use the fourth
   terminal to run a Listener that will monitor that port. The '-'
   filename tells the Listener to write to stdout (see listen.py
   --help for all Listener options):
```
    logger/listener/listen.py --network :6224 --write_file -
```
5. Whew! Now try a few commands in the terminal running the
   LoggerManager (you can type 'help' for a full list):

#### Load a cruise configuration
```
   command? load_cruise test/configs/sample_cruise.json

   command? cruises
     Loaded cruises: NBP1700
```
#### Change cruise modes
```
   command? modes NBP1700
     Modes for NBP1700: off, port, underway

   command? set_mode NBP1700 port
     (You should notice data appearing in the Listener window.)

   command? set_mode NBP1700 underway
     (You should notice more data appearing in the Listener window, and
      the LoggerRunner in the second window should leap into action.)

   command? set_mode NBP1700 off
```

#### Manually change logger configurations
```
   command? loggers NBP1700
     Loggers for NBP1700: knud, gyr1, mwx1, s330, eng1, rtmp

   command? logger_configs NBP1700 s330
     Configs for NBP1700:s330: s330->off, s330->net, s330->file/net/db
   
   command? set_logger_config_name NBP1700 s330 s330->net

   command? set_mode NBP1700 off

   command? quit
```
When setting the mode to port, you should notice data appearing in
the listener window, and should see diagnostic output in the
LoggerManager window.

When setting the mode to underway, you should see more data
appearing in the listener window (due to more logger configs
running), and should see the LoggerRunner leap into action as the
LoggerManager dispatches the configs for "knud.host" to it.

## Server API

The LoggerManager stores and retrieves configuration and status data
using a backing store. There are currently two backing stores
implemented: an in-memory based and Django-based.

By default, a LoggerManager will use the in-memory backing store. This
means that state will be lost whenever the LoggerManager is
restarted. If you have Django installed, you may also specify a
persistent Django backing store via the ```--database`` argument:
```
server/logger_manager.py --websocket localhost:8765 --database django
```

Both backing stores are implemented via and API; for details on the
API and its implementations, please see ```server/server_api.py```,
```server/in_memory_server_api.py```, and
```django_gui/django_server_api.py```.

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
