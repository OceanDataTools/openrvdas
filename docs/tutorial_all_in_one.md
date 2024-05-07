# OpenRVDAS Tutorial and Quickstart
© 2018-2024 David Pablo Cohn - DRAFT 2024-05-06

## Table of Contents

- [Overview - needs and design philosophy](#overview---needs-and-design-philosophy)
  * [Design Philosophy](#design-philosophy)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
  * [Running Loggers](#running-loggers)
  * [Controlling Multiple Loggers](#controlling-multiple-loggers)
  * [Controlling Multiple Loggers via Web Interface](#controlling-multiple-loggers-via-web-interface)
  * [Displaying Logger Data](#displaying-logger-data)
- [Roadmap](#roadmap)
- [More Documentation](#more-documentation)

## Overview - needs and design philosophy

One of the primary values a research vessel offers is the ability to gather accurate and timely scientific data wherever it travels. Most ships carry some combination of oceanographic, meteorological and other sensors. OpenRVDAS - the Open Research Vessel Data Acquisition System - provides a modular and extensible software architecture for gathering, processing, storing, distributing and displaying the data produced by such sensors.

The OpenRVDAS code base has been written from a clean slate based on experience drawn from developing code on behalf of the US Antarctic Program and Antarctic Support Contract, and heavily informed by discussions and collaboration with members of the [RVTEC community](https://www.unols.org/committee/research-vessel-technical-enhancement-committee-rvtec). It is made available free of charge under the [MIT License](https://opensource.org/licenses/MIT).

### Design Philosophy

Every ship will have different requirements, so no single system can hope to accommodate everyone's needs. In addition, those requirements will change from mission to mission and year to year, so no fixed system will be optimal for any length of time.

Because of this, instead of a system, we have focused on designing and building an architecture that allows easy assembly of small, modular components into whatever system is needed in a given situation.

## Software Requirements

OpenRVDAS loggers have been tested on most POSIX-compatible systems running Python 3.6 and above (Linux, MacOS, Windows). Web console monitoring and control are supported for MacOS and most Linux variants (Ubuntu, Red Hat, CentOS, Rocky, Raspbian) and may work on others. The Django-based web interface is designed to be compatible with most modern browsers.

Please see [http://openrvdas.org](http://openrvdas.org) and [http://github.com/oceandatatools/openrvdas](http://github.com/oceandatatools/openrvdas) for the most recent code and documentation.

## Quick Start
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
- class: UDPReader
  kwargs:
    port: 6221

transforms:
- class: SliceTransform  # Strip out the prefix and timestamp
  kwargs:
    fields: "2:"

writers:
- class: TextFileWriter
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

## Logfiles

## Parsing records

## Database connectors

## All the modules

### Creating your own modules

## Controlling Loggers
