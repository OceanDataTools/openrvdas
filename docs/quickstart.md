 OpenRVDAS Tutorial and Quickstart
© 2018-2024 David Pablo Cohn - DRAFT 2024-05-016

## Table of Contents

- [Overview - needs and design philosophy](#overview---needs-and-design-philosophy)
  - [Design Philosophy](#design-philosophy)
- [Software Requirements](#software-requirements)
- [Getting Started](#getting-started)
  - [Get the code](#get-the-code)
  - [Your first logger](#your-first-logger)
  - [Your second logger](#your-second-logger)
- [The listen.py script](#the-listen.py-script)
- [Next things to look at](#next-things-to-look-at)
  - [Writing/reading logfiles](#writing/reading-logfiles)
  - [Parsing records](#parsing-records)
  - [Writing to databases](#writing-to-databases)
  - [Other modules](#other-modules)
  - [Creating your own modules](#creating-your-own-modules)
  - [Record types](#record-types)
- [Next Steps](#next-steps)

## Overview - needs and design philosophy

One of the primary values a research vessel offers is the ability to gather accurate and timely scientific data wherever it travels. Most ships carry some combination of oceanographic, meteorological and other sensors. OpenRVDAS - the Open Research Vessel Data Acquisition System - provides a modular and extensible software architecture for gathering, processing, storing, distributing and displaying the data produced by such sensors.

The OpenRVDAS code base has been written from a clean slate based on experience drawn from developing code on behalf of the US Antarctic Program and Antarctic Support Contract, and heavily informed by discussions and collaboration with members of the [RVTEC community](https://www.unols.org/committee/research-vessel-technical-enhancement-committee-rvtec). It is made available free of charge under the [MIT License](https://opensource.org/licenses/MIT).

### Design Philosophy

Every ship will have different requirements, so no single system can hope to accommodate everyone's needs. In addition, those requirements will change from mission to mission and year to year, so no fixed system will be optimal for any length of time.

Because of this, instead of a system, we have focused on designing and building an architecture that allows easy assembly of small, modular components into whatever system is needed in a given situation.

## Software Requirements

OpenRVDAS loggers have been tested on most POSIX-compatible systems running Python 3.6 and above (Linux, MacOS, Windows). Web console monitoring and control are supported for MacOS and most Linux variants (Ubuntu, Red Hat, CentOS, Rocky, Raspbian) and may work on others. The Django-based web interface is designed to be compatible with most modern browsers.

Please see [http://openrvdas.org](http://openrvdas.org) and [http://github.com/oceandatatools/openrvdas](http://github.com/oceandatatools/openrvdas) for the most recent code and documentation.

## Getting Started
This section will familiarize you with OpenRVDAS and walk you through setting up and running a few simple loggers. These are _not_ the instructions to follow if you want to run it on a ship. If you actually want to set up a proper installation, please read and follow the instructions in [INSTALL.md](../INSTALL.md).

### Get the code
Download from the [OpenRVDAS GitHub repository](https://github.com/OceanDataTools/openrvdas). If you have `git` installed, you would do this by opening a terminal, changing to the directory where you want the code to live (it will create its own `openrvdas` subdirectory here) and running

```buildoutcfg
git clone https://github.com/OceanDataTools/openrvdas.git
```

You can also download a ZIP file of the code from your browser at [https://github.com/OceanDataTools/openrvdas/archive/refs/heads/master.zip](https://github.com/OceanDataTools/openrvdas/archive/refs/heads/master.zip)

### Your first logger
The heart of OpenRVDAS is the __logger__. Loggers read data from some source (typically a sensor), optionally transform it in some or another way (timestamp, parse, perform QC), and then write it somewhere (file, database, network socket).

In OpenRVDAS, these functions are implemented modularly, with __reader__, __transform__ and __writer__ components that can be connected in the desired order to perform the desired functions.

1. Go to the top level OpenRVDAS directory:

```
cd openrvdas
```

2. Create a simple logger configuration. Use the editor of your choice to create a text file named `read_license.yaml` containing the following lines:

```buildoutcfg
# Read the LICENSE file as plain text
readers:
- class: TextFileReader
  kwargs:  # initialization kwargs
    file_spec: LICENSE
    interval: 0.2  # seconds per record, for demo purposes

# Two transforms that will be executed sequentially 
transforms:
- class: TimestampTransform  # has no kwargs
- class: PrefixTransform
  kwargs:
    prefix: "license:"
    
# Write back out as text file. When no filename is given as
# a keyword argument, TextFileWriter writes to stdout.
writers:
- class: TextFileWriter
```

The lines define a logger in YAML format, specifying that we are to read lines of text from the file `LICENSE` at 0.2 seconds per record (for demonstration purposes). We add a timestamp to each record and prefix it with the string `license:`, then write it out as text to standard output.

3. Let's run the logger:

```buildoutcfg
> logger/listener/listen.py --config_file read_license.yaml
license: 2024-05-07T02:35:06.723269Z MIT License
license: 2024-05-07T02:35:07.133440Z Copyright (c) 2017 David Pablo Cohn
license: 2024-05-07T02:35:07.542036Z Permission is hereby granted, free of charge, to any person obtaining a copy
license: 2024-05-07T02:35:07.743469Z of this software and associated documentation files (the "Software"), to deal
license: 2024-05-07T02:35:07.948601Z in the Software without restriction, including without limitation the rights
...
```
### Your second logger

4. Loggers can read from more than one place, by having more than one __reader__, and can write to more than one place, by having more than one __writer__. The following variation reads from the `LICENSE` file as before and echos it to stdout. But it adds a second writer that also writes it via UDP to the local network on port 6221:

```buildoutcfg
# Read the LICENSE file as plain text
readers:
- class: TextFileReader
  kwargs:  # initialization kwargs
    file_spec: LICENSE
    interval: 0.2  # seconds per record, for demo purposes

# Two transforms that will be executed sequentially
transforms:
- class: TimestampTransform  # has no kwargs
- class: PrefixTransform
  kwargs:
    prefix: "license:"

# Write back out as text file. When no filename is given as
# a keyword argument, TextFileWriter writes to stdout.
writers:
- class: TextFileWriter
- class: UDPWriter
  kwargs:
    port: 6221
```
**Note**: Transforms are always performed sequentially, but when a logger has multiple writers, they are all called in parallel with the same data.

Before we run this logger again, let's create a _second_ logger that reads the UDP records. Open a second terminal, go to the `openrvdas` directory and create a second file called `read_udp.yaml`:

```buildoutcfg
readers:
- class: UDPReader  # read UDP records from port 6221
  kwargs:
    port: 6221

transforms:
- class: SliceTransform  # strip out the prefix and timestamp
  kwargs:
    fields: "2:"

writers:
- class: TextFileWriter  # write records to stdout
```
This logger reads records from UDP port 6221, strips out the first two whitespace-separated fields (in this case the 'license:' prefix and timestamp), and outputs the result to standard error.

5. Run this second logger in your second terminal window:

```buildoutcfg
> logger/listener/listen.py --config_file read_udp.yaml
```
6. Initially, nothing should happen, until you actually write something to port 6221 for it to read, by re-running the now-modified first logger in your first terminal window:

```buildoutcfg
> logger/listener/listen.py --config_file read_license.yaml
```
At this point you should see the annotated license file data scrolling through the first window, and the second window should begin displaying those same lines with the prefix and timestamp stripped off.

Congratulations - you've now created and run a couple of OpenRVDAS loggers!

## The listen.py script
The `listen.py` script is a sort of jack-of-all-trades for OpenRVDAS. In addition to loading and running logger configurations from file, it can invoke and run many of the most frequently used modules from the command line. For example, our second logger could have been defined and run from the command line as

```buildoutcfg
logger/listener/listen.py \
    --file LICENSE \
    --transform_timestamp \
    --transform_prefix "license:" \
    --write_file - \
    --write_udp 6221
```
and our UDP-reading logger as

```buildoutcfg
logger/listener/listen.py \
    --udp 6221 \
    --transform_slice "2:" \
    --write_file -
```
The script is very powerful, but also has some non-intuitive gotchas, such as dependencies in the ordering of command line parameters. Please see the dedicated [listen.py document](listen_py.md) for full details.

## Next things to look at
The full complement of OpenRVDAS __readers__, __transforms__ and __writers__ and their functionality can be perused in the repository itself under the `logger/` subdirectory or in the [auto-generated html module documentation](https://htmlpreview.github.io/?https://raw.githubusercontent.com/oceandatatools/openrvdas/master/docs/html/logger/index.html).

To get a sense of a typical set of logger configurations, it is also instructive to look at the loggers defined in the sample cruise definition file for the NB Palmer, in the `configs:` section of [test/NBP1406/NBP1406_cruise.yaml](../test/NBP1406/NBP1406_cruise.yaml).

Note that as a full cruise definition, the file contains multiple configurations for each logger, as well as "cruise modes" that specify which configuration each logger should run in which mode. To better understand cruise definition files, please see the [Controlling Loggers](controlling_loggers.md) document.

### Writing/reading logfiles
While writing raw data to plain text files is a useful start, two modules, `LogfileWriter` and `LogfileReader` allow more refined handling for timestamped data.

If you pass a record that has been timestamped by the `TimestampTransform` to a LogfileWriter, it will get stored in a series of datestamped files rolled over daily using names compatible with the [R2R project conventions](https://www.rvdata.us/). When further processing by another logger is required, `LogfileReader` is able to read these files in a timestamp-aware way.

### Parsing records
Timestamping and storing raw data to log files is useful in itself, but you can unlock much more of the power of OpenRVDAS by having it parse your raw data records into labeled fields that can be plotted, compared and calculated with.

Using a `ParseTransform` you can convert raw records like these:
```
seap 2014-08-01T00:00:00.814000Z $GPZDA,000000.70,01,08,2014,,*6F
seap 2014-08-01T00:00:00.814000Z $GPGGA,000000.70,2200.112071,S,01756.360200,W,1,10,0.9,1.04,M,,M,,*41
seap 2014-08-01T00:00:00.931000Z $GPVTG,213.66,T,,M,9.4,N,,K,A*1E
```
into structured data fields like these:
```
{'data_id': 'seap',
  'fields': {'SeapGPSDay': 1,
             'SeapGPSMonth': 8,
             'SeapGPSTime': 0.7,
             'SeapGPSYear': 2014},
  'timestamp': 1406851200.814},
 {'data_id': 'seap',
  'fields': {'SeapAntennaHeight': 1.04,
             'SeapEorW': 'W',
             'SeapFixQuality': 1,
             'SeapGPSTime': 0.7,
             'SeapHDOP': 0.9,
             'SeapLatitude': 2200.112071,
             'SeapLongitude': 1756.3602,
             'SeapNorS': 'S',
             'SeapNumSats': 10},
  'timestamp': 1406851200.814},
 {'data_id': 'seap',
  'fields': {'SeapCourseTrue': 213.66, 'SeapMode': 'A', 'SeapSpeedKt': 9.4},
  'timestamp': 1406851200.931}]
```

The basic specification of the `ParseTransform` requires only telling it where to look for the appropriate device definition files. This can be done with both the command line interface:

```buildoutcfg
logger/listener/listen.py \
    --udp 6224 \
    --parse_definition_path "local/devices/*.yaml,/opt/openrvdas/local/devices/*.yaml" \
    --transform_parse \
    --write_file -
```
or as part of an OpenRVDAS logger configuration:

```buildoutcfg
    - class: ParseTransform
      kwargs:
        definition_path: test/NBP1406/devices/nbp_devices.yaml
```

For detailed instructions on using the `ParseTransform`, please read the ["Record Parsing" document](parsing.md).

### Writing to databases
#### InfluxDB
OpenRVDAS includes an `InfluxDBWriter` that, as one would expect, writes to the open source time-series database InfluxDB. InfluxDB and its associated graphing package Grafana can be installed and configured by running the script in `utils/install_influx.sh`.

More information on using InfluxDB and Grafana with OpenRVDAS can be found on the [OpenRVDAS Grafana Displays](./grafana_displays.md) page, and on the [InfluxDB](https://www.influxdata.com/) and [Grafana](https://grafana.com/oss/grafana/) project pages.

#### Other databases
OpenRVDAS includes a `DatabaseWriter` that can be configured to run with PostgreSQL, MySQL, MariaDB or MongoDB via a "database connector".

To configure the `DatabaseWriter`, you will need to run the appropriate setup script from the `databases/` subdirectory. The architectures is designed to allow easy addition of other databases by creating of an appropriate database connector class and installation script.

### Other modules
In addition to the standard OpenRVDAS modules under the `logger/` directory, your installation may include additional modules in the `local` and `contrib` directories. They may be used by specifying a module location in the logger configuration:

```buildoutcfg
- class: BME280Reader
  module: contrib.raspberrypi.readers.bme280_reader
  kwargs:
    interval: 60
    temp_in_f: true
    pressure_in_inches: True
```

### Creating your own modules
There is no need to despair if you can't find a module, or combination of modules to do what you need to do. The modularity of OpenRVDAS makes it unreasonably easy to create your own readers, transforms and writers and incorporate them into your workflow.

#### Readers
A reader is simply a Python class that supports a `read()` method that synchronously returns a "record".

#### Transforms
A transform is any Python class that supports a `transform(record)` method that takes some record (or list of records), does something to it/them and returns a record or list of records. It can optionally return `None` if the transformation results in an empty result, as would be the case if your transform were a type of filter.

#### Writers
A writer is any Python class that supports...you guessed it, a `write(record)` method that takes a record or list of records and does something with it. No return value is expected or checked.

In each case, it is good form to link your modules into the repository under the `local/` subdirectory following the guidance in `local/README.md`.

### Record types
Note that while most modules do at least some type checking on their inputs, there is no explicit type-checking of records between modules. It is expected that the configuration designer verify that the output format of each module is compatible with the input format of the modules it feeds into.

## Next Steps
If you only have one or two sensors you intend to log, and wish them to be "always on," then creating a logger configuration file or two and setting them up to run via cron or systemd is a fine and simple solution.

But most practical deployments have a dozen or more sensors/data sources and need to vary what is done with the data of each depending on the ship's location and operational status. The ability to monitor the state of each logger is also essential.

For situations like this, you will want to go ahead and perform a full installation of OpenRVDAS so that you can use its full functionality and the built-in Django-based GUI. Please refer to the [OpenRVDAS GUI Quickstart document](quickstart_gui.md) for an introduction and installation instructions.
