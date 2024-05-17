# The Listener Script - listen.py
© 2018-2019 David Pablo Cohn
 DRAFT 2019-07-20

## Table of Contents

* [Introduction to listen.py](#introduction-to-listenpy)
   * [Specifying configurations on the command line](#specifying-configurations-on-the-command-line)
   * [Examples using the listen.py script](#examples-using-the-listenpy-script)
* [Listener chaining](#listener-chaining)
* [Running more complicated loggers with configuration files](#running-more-complicated-loggers-with-configuration-files)

## Introduction to listen.py

The [listen.py](../logger/listener/listen.py) script incorporates the most common Readers, Transforms and Writers, providing much of the functionality that one might want in a logger straight from the command line. For example, the invocation:

```
logger/listener/listen.py \
  --serial port=/dev/ttyr15,baudrate=9600 \
  --transform_timestamp \
  --transform_prefix gyr1 \
  --write_logfile /log/current/gyr1 \
  --write_udp 6224
```
implements the following data flow:

![Dual writer dataflow](images/dual_writer.png)

In general, the listen.py script runs all of the specified readers in parallel, feeds their output to the specified transforms in series, then feeds the output of the last transform to all the specified writers in parallel:

![Generic listener dataflow](images/generic_listener.png)

### Specifying configurations on the command line

When readers, transforms and writers are specified on the command line, much of the flexibility of listen.py (and therefore much of the opportunity for screwing up) is due to its non-standard convention for parsing those arguments. **Specifically, listen.py parses arguments sequentially in the order in which they appear on the command line.**

The command

```
logger/listener/listen.py \
    --serial port=/dev/ttyr15,baudrate=9600 \
    --transform_timestamp
    --transform_prefix gyr1 \
    --write_logfile /log/current/gyr1
```
will first add a timestamp to records and then prefix 'gyr1' to them, producing:

`gyr1 2017-11-04:05:12:23.318039 $HEHDT,235.95,T*17`

while the command line

```
logger/listener/listen.py \
    --serial port=/dev/ttyr15,baudrate=9600 \
    --transform_prefix gyr1 \
    --transform_timestamp \
    --write_logfile /log/current/gyr1
```
will prefix first, then add a timestamp:

`2017-11-04:05:12:23.318039 gyr1 $HEHDT,235.95,T*17`

Transforms can be applied in any order, and may be repeated as desired, but it is important to remember that because of the sequential processing of the command line, any flags on which a transform (or reader or writer) depends must appear before the transform on the command line. That is:

```
logger/listener/listen.py --udp 6224 \
    --slice_separator ' ' \
    --transform_slice 0:3
```
will slice its records using a space as the field separator, while

```
logger/listener/listen.py --udp 6224 \
    --transform_slice 0:3 \
    --slice_separator ' '  # ignored by the preceding transform
```
will use the default separator (a comma), because the `--slice_separator` argument comes after the `--transform_slice` argument that it is (presumably) supposed to act upon.

### Examples using the listen.py script

For all its limitations, the listen.py script has a lot of tricks up its sleeve. Here's a simple invocation to read from a serial port and write to a "normal" file:

```
logger/listener/listen.py \
    --serial port=/dev/ttyr15 \
    --write_file my_file
```
If your machine doesn't have any serial ports sending actual data, you can create virtual serial ports, as described in [Simulating Live Data](simulating_live_data.md), by running

```
logger/utils/simulate_data.py \
    --port /tmp/tty_gyr1 \
    --filebase test/NBP1406/gyr1/raw/NBP1406_gyr1-2014-08-01
```
in a separate terminal, in which case your listener command line would be

```
logger/listener/listen.py \
    --serial port=/tmp/tty_gyr1 \
    --write_file my_file
```
To see what is going on, specify '-' as the file argument, which tells the TextFileWriter to write to stdout:

```
logger/listener/listen.py \
    --serial port=/tmp/tty_gyr1 \
    --write_file -
```
You should see output like this:

```
$HEHDT,235.77,T*1b
$HEHDT,235.85,T*16
$HEHDT,235.91,T*13
...
```
If you want to see more of what's going on, you can re-run the above commands with `-v` (to set logging level to "info") or `-v -v` (to set it to "debug").

Let's go ahead and attach a timestamp to the data we receive, prefix it by the instrument name, and send it to the network, say port 6224, in addition to stdout:

```
logger/listener/listen.py \
    --serial port=/tmp/tty_gyr1 \
    --transform_timestamp \
    --transform_prefix gyr1 \
    --write_udp 6224 \
    --write_file -
```
producing

```
gyr1 2019-06-25T20:52:28.152794Z $HEHDT,218.40,T*10
gyr1 2019-06-25T20:52:28.153415Z $HEHDT,218.36,T*11
gyr1 2019-06-25T20:52:28.317247Z $HEHDT,218.33,T*14
gyr1 2019-06-25T20:52:28.518668Z $HEHDT,218.29,T*1f
...
```
(An error "Network is unreachable" may occur if you're offline.)

You can also read directly from one or more network ports:

```
logger/listener/listen.py \
    --udp 6224,6225 \
    --write_file -
```
and filter the results to only receive records of interest:

```
logger/listener/listen.py \
    --udp 6224,6225 \
    --transform_regex_filter "^gyr1 " \
    --write_file -
```
If our network records look like

```
gyr1 2019-06-25T20:52:28.721599Z $HEHDT,218.24,T*12
```

we can strip off the instrument name before storing it:

```
logger/listener/listen.py \
    --udp 6224,6225 \
    --transform_regex_filter "^gyr1 " \
    --transform_slice 1: \
    --write_file -
```
which uses Python-style list indexing to select elements in a line of space-delimited fields (the `--slice_sep` argument allows specifying whatever delimiter is appropriate). The SliceTransform accepts arbitrary comma-separated indices, such as `--transform_slice -1,2:4,-2,0`.

Logfile records are special in that they are prefixed with timestamps. If, for testing or display purposes, we want our LogfileReader to deliver the records in intervals that correspond to the intervals between their timestamps, we can specify so with a flag:

```
logger/listener/listen.py \
    --logfile_use_timestamps \
    --logfile test/NBP1406/gyr1/raw/NBP1406_gyr1-2014-08-01 \
    --write_file -
```
To read logfiles in parallel, we can either specify a comma-separated list of logfiles:

```
logger/listener/listen.py \
    --logfile_use_timestamps \
    --logfile test/NBP1406/gyr1/raw/NBP1406_gyr1-2014-08-01,test/NBP1406/knud/raw/NBP1406_knud-2014-08-01 \
    --write_file -
```
or specify them with two separate `--logfile` flags:

```
logger/listener/listen.py \
    --logfile_use_timestamps \
    --logfile test/NBP1406/gyr1/raw/NBP1406_gyr1-2014-08-01 \
    --logfile test/NBP1406/knud/raw/NBP1406_knud-2014-08-01 \
    --write_file -
```
It's worth taking a moment to discuss how listen.py and its FileReaders and LogfileReaders select and read through the files that are specified as their inputs.

A FileReader takes a wildcarded filename and open the matching files in alphanumeric order, going on to the next when it reaches EOF of the previous file. Note that FileReaders also accept a `--tail` argument that says not to return EOF on reaching the end of the last file, but to continue checking for more input, as well as a `--refresh_file_spec` flag that further instructs it to check whether any new files matching the specification have appeared in the meantime.[^2]

So the invocation

```
logger/listener/listen.py \
    --tail --refresh_file_spec \
    --file test/NBP1406/\*/raw/NBP1406_\* \
    --write_file -
```
will create a single FileReader that will sequentially read through and deliver the records of all logfiles in the test directory, then wait to see if any more matching files ever show up. In contrast, each **comma-separated** value is used to instantiate a separate reader, as above.

A LogfileReader is effectively a FileReader that understands and makes approximate use of the R2R naming conventions for logfiles,[^3] specifically that records for each instrument are logged in a file appended by the date of those records. So records for a gyroscope run the first three days of November might be stored as

```
NBP1700_gyr1-2017-11-01
NBP1700_gyr1-2017-11-02
NBP1700_gyr1-2017-11-03
```
Records within a logfile are also expected to be prefixed by a timestamp, the default format of which is encoded in timestamp.py

When creating a LogfileReader, we give it a filebase (e.g. `NBP1700/gyr1/raw/NBP_gyr1`) and it knows to append a wildcard to the name and read through all files on the specified path bearing that name and a date suffix. For example,

```
logger/listener/listen.py \
    --logfile_use_timestamps \
    --logfile test/NBP1406/gyr1/raw/NBP1406_gyr1 \
    --write_file -
```
Will match all files that have `NBP1406/gyr1/raw/NBP1406_gyr1` as their prefix and deliver the records they contain in sequence. As we've already observed, an additional power of LogfileReaders is that they can also parse the timestamps of their records and deliver them at a rate corresponding to their original creation times.

So, given these pieces, let's try reading data from a logfile, stripping off the timestamps and creating new timestamps that are more spread out, simulating a faster delivery of data.

```
logger/listener/listen.py \
    --logfile test/NBP1406/gyr1/raw/NBP1406_gyr1 \
    --transform_slice 1: \
    --transform_timestamp \
    --write_logfile /tmp/NBP1406_fast_gyr \
    --interval 0.1
```
Note that we've left off the `--logfile_use_timestamps` flag, so the LogfileReader will read its records as fast as it can. We slice off the first field in the record (the old timestamp), add a new one, and write it to a new logfile. We also specify `--interval 0.1` to tell the listener to sleep so that (as close as it can manage) new records come out every 0.1 seconds.

If you append `-v -v` to the above call to place the listener in debug mode, you'll get to see all the inner workings as the LogfileReader instantiates an inner TextFileReader, fetches records from it, slices off the first field, adds a new timestamp and writes it to a date-stamped logfile.

## Listener chaining

While the previous section illustrates the flexibility of the listen.py script, there are still limitations. When running from the command line, **all** transforms are applied to **all** records from **all** readers, before being sent out to **all** writers. In our original custom logger, records sent to the UDPWriter were prefixed with the instrument name ('gyr1'), while records that were written to the gyr1 logfile (where the prefix would be redundant) were not.

One way around this problem is **listener chaining**.

Chaining is just the process of running multiple instances of the script in parallel, for example:

```
logger/listener/listen.py \
    --serial port=/dev/ttyr15,baudrate=9600 \
    --transform_timestamp \
    --write_logfile /log/current/gyr1 &

logger/listener/listen.py \
    --logfile /log/current/gyr1 \
    --transform_prefix gyr1 \
    --write_udp 6224
```
The first of these scripts timestamps records as they come in and saves them in a log file. The second one reads that logfile, adds the desired prefix, and broadcasts it to the network via UDP. Surprisingly complex workflows can be achieved with chaining.

## Running more complicated loggers with configuration files

For logger workflows of non-trivial complexity, we recommend that users forgo specifying Readers, Transforms and Writers on the command line in favor of using configuration files.

A configuration file is a YAML or JSON specification[^4] of components along with their parameters. It may be invoked using the `--config_file` argument:

```
logger/listener/listen.py --config_file gyr_logger.yaml
```
where gyr_logger.yaml consists of the YAML definition

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
The basic format of a logger configuration file is a YAML or JSON definition:

```
  readers: [... ]
  transforms: [...]
  writers: [...]
```
where the reader/transform/writer definition is a list of dictionaries, each defining one component via two elements: a "class" key defining the type of component, and a "kwargs" key defining its keyword arguments:

```
  class: LogfileWriter
  kwargs:
    filebase: /log/current/gyr1
```
If there is only one component defined for readers/transforms/writers, it doesn't need to be enclosed in a list, as with the "readers" example above.

One major advantage of using configuration files is the ability to use ComposedReaders and ComposedWriters, containers that allow efficient construction of sophisticated dataflows.

You may also load a single configuration from a complete cruise definition file by separating the file name from the configuration name with a colon:

```
  listen.py --config_file test/NBP1406/NBP1406_cruise.yaml:'gyr1->net' -v
```
This functionality has proven useful for debugging a logger that is dying mysteriously.

Please see [OpenRVDAS Configuration Files](configuration_files.md) for
a more complete description of the configuration file model, and
[simple_logger.py](../test/configs/simple_logger.yaml),
[composed_logger.py](../test/configs/composed_logger.yaml) and
[parallel_logger.py](../test/configs/parallel_logger.yaml) in the
project's [test/configs](../test/configs) directory for examples.

[^1]: YAML is a strict superset of JSON, modulo the restriction that it may not use tabs as whitespace.
