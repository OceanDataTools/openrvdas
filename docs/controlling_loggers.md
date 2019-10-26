# OpenRVDAS Controlling Loggers
© 2018-2019 David Pablo Cohn - DRAFT 2019-10-04

## Overview

The [OpenRVDAS Introduction and Overview](intro_and_overview.md) document provides an introduction to the OpenRVDAS framework, and [Introduction to Loggers](intro_to_loggers.md) provides an introduction to the process of running *individual* loggers.

This document describes two scripts that allow running, controlling and monitoring entire sets of loggers: [logger\_runner.py](../server/logger_runner.py) and [logger\_manager.py](../server/logger_manager.py).

## Table of Contents

* [The high-order bits](#the-high-order-bits)
* [The logger_runner.py script](#logger_runnerpy)
* [The logger_manager.py script](#logger_managerpy)
   * [Cruises, modes and configurations](#cruises-modes-and-configurations)
   * [What the logger manager does](#what-the-logger-manager-does)
   * [Running logger_manager.py from the command line](#running-logger_managerpy-from-the-command-line)
   * [Driving widget-based data display with the logger_manager.py](#driving-widget-based-data-display-with-the-logger_managerpy)
   * [Web-based control of the logger_manager.py](#web-based-control-of-the-logger_managerpy)
   * [Managing loggers via a web interface](#managing-loggers-via-a-web-interface)

## The High-Order Bits

The ``listen.py`` script will run a single logger defined either from command line parameters, or by loading a logger configuration file. The ``logger_runner.py`` script will run a set of loggers loaded from a configuration file whose format is a YAML/JSON map:

```
  logger1_name:
    logger1_configuration
  logger2_name:
    logger2_configuration
  ...
  
```

If a logger dies, the logger runner will restart it a specified number
of times.

The ``logger_manager.py`` script take a more complicated file (called
a "cruise definition file") that consists not only of a list of named
configurations, but also of "modes" such as "off", "in port" and
"underway", specifying which configurations should be running in which
mode. In addition to using a logger runner to run the loggers for the
current mode, it supports and API that lets one control and monitor it
from the command line or via a web interface.

In the default installation, a logger manager and its companion, the
cached data server, are run by the system's ``supervisor``
daemon.

Below, we go into greater detail on these points.

## logger\_runner.py

The [listen.py](listen_py.md) script is handy for running a single logger from the command line. For more sophisticated logger management, the [logger\_runner.py](../server/logger_runner.py) script is provided. It takes as its input a YAML or JSON file defining a dict of configurations that are to be run, where the keys are (convenient) configuration names, and the values are the logger configurations themselves.

```server/logger_runner.py --config test/config/sample_configs.yaml -v```

The sample_configs.yaml file should be a YAML-formatted dictionary:

```
eng1->net:
  name: eng1->net
  readers:
    class: SerialReader
    kwargs:
      baudrate: 9600
      port: /tmp/tty_eng1
  transforms:
  - class: TimestampTransform
  - class: PrefixTransform
    kwargs:
      prefix: eng1
  writers:
    class: UDPWriter
    kwargs:
      port: 6224
gyr1->net:
  ...
knud->net:
  ...
s330->net:
  ...
```

where each logger configuration is in the format described in the
[Configuration Files](configuration_files.md) document.

Note that the provided test/config/sample_configs.yaml specifies
configurations that read simulated data from virtual serial ports. To
create those ports and begin feeding them with data, you'll need to
run

```
logger/utils/simulate_serial.py --config test/serial_sim.yaml --loop
```
in a separate terminal. To observe the data being logged by the above sample configs, you can start a Listener in yet another terminal:

```
logger/listener/listen.py --udp 6224
```
Please see the [server/README.md](../server/README.md) file and [logger_runner.py](../server/logger_runner.py) headers for the most up-to-date information on running logger\_runner.py.

## logger\_manager.py

The logger\_runner.py script will run a set of loggers and retry them if they fail, but it doesn't provide any way of modifying their behaviors other than killing them all and re-running with a new set of configurations. The [logger\_manager.py](../server/logger_manager.py) script is a powerful wrapper around logger\_runner.py that offers much additional functionality.

### Cruises, modes and configurations

Before we dive into the use of logger\_manager.py, it's worth pausing for a moment to introduce some concepts that underlie the structure of the logger manager. _(Note: much of this section could be moved to [OpenRVDAS Configuration Files](configuration_files.md))._

-   **Logger configuration** - This is a definition for a set of Readers, Transforms and Writers feeding into each other, such as would be read using the --config argument of the listen.py script. In OpenRVDAS, each logger configuration that is active runs as its own daemon process.  The sample logger configuration below ("knud-\>net") reads NMEA data from the Knudsen serial port, timestamps and labels the record, then broadcasts it via UDP:

```
  knud->net: 
    host_id: knud.host
    name: knud->net
    readers: 
      class: SerialReader
      kwargs: 
        port: /tmp/tty_knud
        baudrate: 9600
    transforms: 
    - class: TimestampTransform
    - class: PrefixTransform
      kwargs: 
        prefix: knud
    writers: 
      class: UDPWriter
      kwargs: 
        port: 6224
```
-   **Cruise mode (or just "mode")** - Logger configurations can be grouped into logical collections that will be active at any given time. Certain logger configurations will be running when a vessel is in port; another set may be running while the vessel is at sea, but within territorial waters; yet another when it is fully underway. The mode definition below indicates that when "port" mode is active, the configurations "gyr1-\>net", "mwx1-\>net", "s330-\>net" and "eng1-\>net" should be running:

```
  modes:  
    off:  
      gyr1: gyr1->off 
      mwx1: mwx1->off 
      s330: s330->off 
      eng1: eng1->off 
      knud: knud->off 
      rtmp: rtmp->off 
    port:  
      gyr1: gyr1->net 
      mwx1: mwx1->net 
      s330: s330->net 
      eng1: eng1->net 
      knud: knud->off 
      rtmp: rtmp->off 
    underway:
      gyr1: gyr1->file/net/db 
      mwx1: mwx1->file/net/db 
      s330: s330->file/net/db 
      eng1: eng1->file/net/db 
      knud: knud->file/net/db 
      rtmp: rtmp->file/net/db
```
-   **Cruise configuration** - (or just "configuration" when we're being sloppy). This is the file/JSON/YAML structure that contains everything the logger manager needs to know about running a cruise. In addition to containing cruise metadata (cruise id, provisional start and ending dates), a cruise configuration file (such as in [test/NBP1406/NBP1406\_cruise.yaml](../test/NBP1406/NBP1406_cruise.yaml)), contains a dict of all the logger configurations that are to be run on a particular vessel deployment, along with definitions for all the modes into which those logger configurations are grouped.
  
It is worth noting that strictly speaking, a "logger" does not exist as a separate entity in OpenRVDAS. It is just a convenient way of thinking about a set of configurations that are responsible for a given data stream, e.g. Knudsen data, or a GPS feed. This is evident when looking at the [sample cruise definition file](../test/NBP1406/NBP1406_cruise.yaml), as the logger definition ("knud") is just a list of the configurations that are responsible for handling the data that comes in from a particular serial port.

```
knud:
  configs:
  - knud->off,
  - knud->net,
  - knud->file/net/db
```
Perusing a complete cruise configuration file such as [test/NBP1406/NBP1406_cruise.yaml](../test/NBP1406/NBP1406_cruise.yaml) may be useful for newcomers to the system.

### What the logger manager does

In short, a bunch of stuff.

![Logger Manager Diagram](images/logger_manager_diagram.png)

* It spawns a command line console interface to a database/backing
  store where it will store/retrieve information on which logger
  configurations should be running and which are. By default, this
  database will be an in-memory, transient store, unless overridden
  with the ``--database`` flag to select ``django`` or
  ``hapi``). When run as a service, the console may be disabled by
  using the ``--no-console`` flag:

  ```
  server/logger_manager.py --database django --no-console
  ```

* If a cruise definition and optional mode are specified on the
  command line via the ``--config`` and ``--mode`` flags, it loads
  the definition into the database and sets the current mode as
  directed:

  ```
  server/logger_manager.py \
        --config test/NBP1406/NBP1406_cruise.yaml \
        --mode monitor
  ```

* It consults the database to determine what loggers, logger
  configurations and cruise modes exist, and which cruise mode or
  combination of logger configurations the user wishes to have running
  and starts/stops logger processes as appropriate. It records the new
  logger states in the database. Once started, it monitors the health
  of theses processes, recording failures in the database and
  restarting processes as necessary.

### Running logger\_manager.py from the command line

As indicated above, the logger\_manager.py script can be run with no arguments and will default to using an in-memory data store:

```
server/logger_manager.py
```
You can type "help" for a full list of commands, but a sample of the available functionality is

**Load a cruise configuration**

```
command? load_configuration test/NBP1406/NBP1406_cruise.yaml
command? 
```

**See what loggers are defined**

```
command? get_loggers
Loggers: PCOD, adcp, eng1, gp02, grv1, gyr1, hdas, knud, mbdp, mwx1, pco2, pguv, rtmp, s330, seap, svp1, true_winds, tsg1, tsg2
command?
```

**Get and change cruise modes**

```
command? get_modes
Available Modes: off, port, monitor, monitor and log
command? get_active_mode
Current mode: off
command? set_active_mode port
command? 
```

**Note**: the NBP1406 sample cruise directs UDP output to port 6224, so you can monitor the logger manager's network output by running the following listener command in a separate window to read from port 6224 and write to standard output:

```
    logger/listener/listen.py --udp 6224 --write_file -
```

**Manually change logger configurations**

```
command? get_logger_configs gyr1
Configs for gyr1: gyr1->off, gyr1->net, gyr1->file/net/db
command? set_active_logger_config gyr1 gyr1->file/net/db
command? quit
```
As with sample script for logger\_runner.py, the sample cruise configuration file [test/NBP1406/NBP1406\_cruise.yaml](../test/NBP1406/NBP1406\_cruise.yaml) attempts to read from virtual serial ports, so you'll need to create those simulated serial ports by having the command

```
  logger/utils/simulate_serial.py \
      --config test/NBP1406/serial_sim_NBP1406.yaml \
      --loop
```

running in another terminal for the logger manager to load and run it without complaining.


### Driving widget-based data display with the logger\_manager.py

In addition to being stored, logger data may be displayed in real time
via [display widgets](display_widgets.md). The most straightforward
way to do this is by configuring loggers to echo their output to a
[CachedDataServer](../logger/utils/cached_data_server.py). This may be
done either via UDP (if the CachedDataServer has been initialized to
listen on a UDP port) or via CachedDataWriter that will connect using
a websocket. Widgets on display pages will then connect to the data server
via a websocket and request data, as described in the [Display Widgets
document](display_widgets.md).

![Logger Manager with CachedDataServer](images/console_based_logger_manager.png)

A CachedDataServer may be run as a standalone process, but it may also
be invoked by the LoggerManager when handed a ``--start_data_server``
flag:

```
  server/logger_manager.py \
    --database django \
    --config test/NBP1406/NBP1406_cruise.yaml \
    --data_server_websocket 8766 \
    --start_data_server
```

The CachedDataServer may be invoked to also listen for data on a UDP
port. This parameter may be passed along by the logger manager via an
additional command line flag:

```
  server/logger_manager.py \
    --database django \
    --config test/NBP1406/NBP1406_cruise.yaml \
    --data_server_websocket 8766 \
    --data_server_udp 6226 \
    --start_data_server
```

When the logger manager has been invoked with a data server websocket
address, it will publish its own status reports to the
CachedDataServer at that that address. The fields it will make
available are ``status:cruise_definition`` for the list of logger
names, configurations and active configuration, and
``status:logger_status`` for actual running state of each logger.

### Web-based control of the logger_manager.py

In addition to being controlled from a command line console, the
logger\_manager.py may be controlled by a web console.

![Logger Manager with
 CachedDataServer](images/web_based_logger_manager.png)

If the system is installed using the default build scripts in the
[utils directory](../utils), it will be configured to serve a
Django-based web console served by Nginx. The logger manager will be
configured to use the Django-based database (backed by MySQL/MariaDB) to
maintain logger state.

But while the system will use Django and the webserver to load the web
console HTML and Javascript, the loaded Javascript will look for a
CachedDataServer from which to draw information about what loggers are
and should be running.

In the default installation, the Linux ``supervisor`` daemon is configured to be able to run and monitor both the logger manager and CachedDataServer on demand. The configuration file for this is in ``/etc/supervisor/conf.d/openrvdas`` on Ubuntu and ``/etc/supervisord/openrvdas.ini`` on CentOS/RedHat:

```
[program:cached_data_server]
command=/usr/bin/python3 server/cached_data_server.py --port 8766 --disk_cache /var/tmp/openrvdas/disk_cache --max_records 86400 -v
directory=${INSTALL_ROOT}/openrvdas
autostart=$SUPERVISOR_AUTOSTART
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/cached_data_server.err.log
stdout_logfile=/var/log/openrvdas/cached_data_server.out.log
user=$RVDAS_USER

[program:logger_manager]
command=/usr/bin/python3 server/logger_manager.py --database django --no-console --data_server_websocket :8766 -v
directory=${INSTALL_ROOT}/openrvdas
autostart=$SUPERVISOR_AUTOSTART
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/logger_manager.err.log
stdout_logfile=/var/log/openrvdas/logger_manager.out.log
user=$RVDAS_USER
```

The servers may be started/stopped either via the local webserver at [http://openrvdas:8001](http://openrvdas:8001) (assuming your machine is named 'openrvdas') or via the command line ``supervisorctl`` tool:

```
  root@openrvdas:~# supervisorctl
  cached_data_server               STOPPED   Oct 05 03:22 AM
  logger_manager                   STOPPED   Oct 05 03:22 AM
  simulate_nbp_serial              STOPPED   Oct 05 03:22 AM

  supervisor> start cached_data_server logger_manager
  cached_data_server: started
  logger_manager: started

  supervisor> status
  cached_data_server               RUNNING   pid 5641, uptime 0:00:04
  logger_manager                   RUNNING   pid 5646, uptime 0:00:03
  simulate_nbp_serial              STOPPED   Oct 05 03:22 AM

  supervisor> exit
```

and, as you may see from the configuration file, stderr and stdout for
the processes will be written to appropriately-named files in
`/var/log/openrvdas``.

You will have noticed that many of the examples in this documentation
make use of the ``NBP1406`` sample cruise definition, and that using
that example requires creating and feeding simulated serial ports. As
a convenience, the supervisor configuration file also contains a
definition that lets you create and feed those ports via
supervisorctl:

```
  root@openrvdas:~# supervisorctl
  cached_data_server               RUNNING   pid 5641, uptime 0:12:00
  logger_manager                   RUNNING   pid 5646, uptime 0:11:59
  simulate_nbp_serial              STOPPED   Oct 05 03:22 AM

  supervisor> start simulate_nbp_serial
  simulate_nbp_serial: started

  supervisor> status
  cached_data_server               RUNNING   pid 5641, uptime 0:12:13
  logger_manager                   RUNNING   pid 5646, uptime 0:12:12
  simulate_nbp_serial              RUNNING   pid 5817, uptime 0:00:05

  supervisor> exit
```

Please see the [server/README.md](../server/README.md) file and [logger_manager.py](../server/logger_manager.py) headers for the most up-to-date information on running logger\_manager.py.

### Managing loggers via a web interface

There is a Django-based GUI for controlling logger\_manager.py via a web interface. If you have installed OpenRVDAS using one of the utility installation scripts described in the appendix, they will have installed the NGINX web server and logger\_manager.py to run as system services. Please see the [Django Web Interface](django_interface.md) document and [django_gui/README.md](../django_gui/README.md) for up-to-date information.


