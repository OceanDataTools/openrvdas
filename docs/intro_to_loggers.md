# OpenRVDAS Introduction to Loggers
© 2018 David Pablo Cohn - DRAFT 2018-12-15

One of the primary values a research vessel offers is the ability to gather accurate and timely scientific data wherever it travels. Most ships carry some combination of oceanographic, meteorological and other sensors and operate a system - a Research Vessel Data Acquisition System, or RVDAS - for storing, processing, analyzing and displaying the data they produce.

The basic unit of an RVDAS is a "logger" - a process or set of processes that read from a sensor and store the data, optionally processing it for display, analysis or combination with other acquired data.

This document describes the construction and operation of individual OpenRVDAS loggers. Please see [Controlling Loggers](controlling_loggers.md) for information on running/controlling multiple loggers, and see the [Quickstart Document](quickstart.md) quick introduction.

## Table of Contents

* [Logger Architecture](#logger-architecture)
* [Building and Running Loggers at the Code Level](#building-and-running-loggers-at-the-code-level)
* [Using the Listener Class](#using-the-listener-class)
* [Using the Listen Script](#using-the-listen-script)
* [Logger Configuration Files](#logger-configuration-files)

## Logger Architecture

As described in the introduction and overview, we recognize that every ship will have different requirements, so we have focused on designing and building an architecture that allows easy assembly of small, modular components into whatever system is needed in a given situation.

The core logger architecture is made up of three basic classes of components: Readers, Transforms, and Writers that can be "snapped together" to produce the necessary functionality. We have specified a simple API for these components and implemented a handful of the most useful ones in Python.

![Reader, Transform and Writer](images/read_transform_write.png)

## Building and Running Loggers at the Code Level

If we want to work down at the code level, we can combine Reader, Transform and Writer components in a very few lines of Python to build a full-fledged logger that reads an instrument serial port, timestamps and stores the record to file, and forwards it via UDP for displays or other waiting processes:

```
def logger(port, instrument):
  reader = SerialReader(port=port, baudrate=9600)
  ts_transform = TimestampTransform()
  prefix_transform = PrefixTransform(instrument)
  network_writer = UDPWriter(6224)
  logfile_writer = LogfileWriter('/log/current/%s' % instrument)
  
  while True:
    record = reader.read()
    timestamped_record = ts_transform.transform(record)
    prefixed_record = prefix_transform.transform(timestamped_record)
    logfile_writer.write(timestamped_record)
    network_writer.write(prefixed_record)
```

![UDPWriter data flow](images/network_writer.png)

The document [OpenRVDAS Components](components.md) describes many of the currently-implemented Readers, Transforms and Writers, and you can examine the directories [logger/readers/](../logger/readers), [logger/transforms/](../logger/transforms) and [logger/writers/](../logger/writers) for the full set of standard, implemented components.

## Using the Listener Class

A ```Listener``` class further simplifies creation and running of loggers at the code level. It takes a list of Readers, Transforms and Writers and runs them in an "hourglass" pipeline:

![Hourglass dataflow for listener class](images/generic_listener.png)

It runs all Readers in parallel, feeding their output to the Transforms, run in series, and feeding that output to the Writers, run in parallel, as below:

```
    listener = Listener(readers=[UDPReader(6221),
                                 UDPReader(6223)],
                        transforms=[TimestampTransform(),
                                    PrefixTransform('network')],
                        writers=[TextFileWriter('/logs/network_recs'),
                                 DatabaseWriter()]
                       )
    listener.run()
```

Please see the code in [logger/listener/listener.py](../logger/listener/listener.py) for more information about using the Listener class.

## Using the Listen Script

The [logger/listener/listen.py](../logger/listener/listen.py) script is a convenient wrapper around the Listener class, and allows combining and running the most commonly-used Reader, Transform and Writer components from the command line. For example, the invocation:

```
listen.py \
  --serial port=/dev/ttyr15,baudrate=9600 \
  --transform_timestamp \
  --transform_prefix gyr1 \
  --write_logfile /log/current/gyr1 \
  --write_udp 6224
```
implements the following data flow:

![Dual writer dataflow](images/dual_writer.png)

The listen.py script and its (sometimes non-intuitive) command line options are described in greater detail in the [Listen.py Script](listen.py.md) document.

## Logger Configuration Files

For logger workflows of non-trivial complexity, we recommend that users forgo specifying Readers, Transforms and Writers on the command line in favor of using configuration files.

A configuration file is a YAML or JSON (a subset of YAML) specification of components along with their parameters. It may be invoked using the `--config_file` argument:

```
logger/listener/listen.py --config_file gyr_logger.yaml
```

The file gyr_logger.yaml might consist of the YAML/JSON definition

```
  readers:  
    class: SerialReader 
    kwargs:  
      port: /dev/ttyr15 
      baudrate: 9600 
  transforms:
  - class: TimestampTransform  # NOTE: no keyword args 
  - class: PrefixTransform 
    kwargs:  
      prefix: gyr1 
  writers:
  - class: LogfileWriter 
    kwargs:  
      filebase: /log/current/gyr1 
  - class: UDPWriter 
    kwargs: 
      port: 6224 
```

The listen.py script may also read a specific logger config from a cruise definition file, e.g.:

```
# Run the gyr1->net config from cruise definition NBP1406_cruise.yaml
logger/listener/listen.py --config_file test/NBP1406/NBP1406_cruise.yaml:"gyr1->net"
```

This functionality is especially handy when trying to debug new logger configurations.

Again, use of listen.py script with and without configuration files is described in [The Listener Script](listen_py.md), and  configuration files are described in detail in [OpenRVDAS Configuration Files](configuration_files.md).

Multiple loggers may be run together and controlled from the command line, via an API or a web interface using the logger\_manager.py and logger_runner.py scripts described in the [Controlling Loggers](controlling_loggers.md) document.

Data produced by loggers may be visualized via display widgets, as described in the [Display Widgets](display_widgets.md) document.
