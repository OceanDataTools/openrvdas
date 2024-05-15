# OpenRVDAS Components
Draft 2019-07-20
© 2018 David Pablo Cohn

This document enumerates and describes current OpenRVDAS Reader, Writer
and Transform components. For background on using them, please see the
[OpenRVDAS Introduction to Loggers](intro_to_loggers.md).

## Contents

* [Introduction to Components](#introduction-to-components)
* [Using the Listener Class](#using-the-listener-class)
* [Composed Readers and Writers](#composed-readers-and-writers)
* [Using Configuration Files](#using-configuration-files)
* [Components](#components)
  * [Readers](#readers)
  * [Writers](#writers)
  * [Transforms](#transforms)
  * [Future Components](#future-components)
  
## Introduction to Components

The core of OpenRVDAS are three types of simple components designed to be
"snapped together" to create arbitrarily powerful data flows.

* **Readers** (e.g. SerialReader, NetworkReader, LogfileReader, DatabaseReader) implement a `read()` method that retrieves a data record from somewhere and returns it.

  ```
  reader = SerialReader(port='/dev/ttyr15', baudrate=9600)
  record = reader.read()
  ```

* **Transforms** (e.g. TimestampTransform, ParseTransform, FilterTransform) implement a `transform()` method that takes a record as input and returns some transformed version of it.

  ```
  ts_transform = TimestampTransform()
  prefix_transform = PrefixTransform('gyr1')

  timestamped_record = ts_transform.transform(record)
  prefixed_record = prefix_transform.transform(timestamped_record)
  ```

* **Writers** (e.g. LogfileWriter, UDPWriter, DatabaseWriter) implement - you guessed it - a `write()` method that takes a record and stores/or distributes it in some way.

  ```
  udp_writer = UDPWriter(port=6224)
  logfile_writer = LogfileWriter('/log/current/gyr1')

  logfile_writer.write(timestamped_record)
  udp_writer.write(prefixed_record)
  ```

As described in [OpenRVDAS Introduction to Loggers](intro_to_loggers.md), we can combine these components to create simple and powerful loggers:

```
def logger(port, instrument):
  reader = SerialReader(port=port, baudrate=9600)
  ts_transform = TimestampTransform()
  prefix_transform = PrefixTransform(instrument)
  udp_writer = UDPWriter(6224)
  logfile_writer = LogfileWriter('/log/current/%s' % instrument)

  while True:
    record = reader.read()
    timestamped_record = ts_transform.transform(record)
    prefixed_record = prefix_transform.transform(timestamped_record)

    logfile_writer.write(timestamped_record)
    udp_writer.write(prefixed_record)
```

## Using the Listener Class

The Listener class (defined in [logger/listener/listen.py](../logger/listener/listen.py)) at the heart of the listen.py script makes combining readers, transforms and writers in Python even simpler. It takes a list of one or more Readers, a list of zero or more Transforms, and zero or more Writers and pipes them together. The code

```
listener = Listener([reader1, reader2, reader3],
                    [transform1, transform2],
                    [writer1, writer2, writer3])
listener.run()
```
implements the following dataflow:

![Generic listener](images/generic_listener.png)
 
As with simple invocation of the listen.py script, all readers are called in parallel, via separate threads. The values they return are passed through each transform in series, then distributed to the writers, where they are written in parallel. But in this case we have greater control over the configurations of each component than the command line interface allows, including control over in which order transforms are applied.

To implement the dataflow we initially described with a Listener, we would specify:

```
readers = SerialReader(port=port, baudrate=9600)
transforms = TimestampTransform()
writers = [LogfileWriter(filebase='/log/current/%s' % instrument),
           ComposedWriter(transforms=[PrefixTransform(instrument)],
                          writers=[UDPWriter(6224)])]
listener = Listener(readers=readers, transforms=transforms, writers=writers)
listener.run()
```

Note that we've used one of the as-yet-unintroduced tricks of the architecture above: a ComposedWriter.

## Composed Readers and Writers

A ComposedWriter is just a structural wrapper that connects a list of Transforms (again in series) with a set of Writers (again in parallel), and packages it up to look like a simple writer:

![Composed Writer](images/composed_writer.png)

By wrapping our PrefixTransform and NetworkWriter into a ComposedWriter, we achieve the desired dataflow:

![Using a Composed Writer](images/using_a_composed_writer.png)

Unsurprisingly, there is also a ComposedReader that takes a list of one or more Readers (which it runs in parallel) and one or more Transforms (which it runs in series):

![Composed Reader](images/composed_reader.png)

## Using Configuration Files

It is not necessary to write Python code to assemble your desired set of components. There are subclasses of Listener (ListenerFromLoggerConfig() and ListenerFromLoggerConfigFile()) that take read YAML/JSON configuration files and assemble the specified components for execution.

Let us say we have the following specification in file `gyr1_config.yaml`:

```
{
  "readers": {
    "class": "SerialReader",
    "kwargs": {
      "port": "/dev/ttyr15",
      "baudrate": 9600
    }
  },
  "transforms": [
    {
      "class": "TimestampTransform"
    }
  ],
  "writers": [
    {
      "class": "LogfileWriter",
      "kwargs": {
        "filebase": "/log/current/gyr1"
      }
    },
    {
      "class": "ComposedWriter",
      "kwargs": {
        "transforms": {
          "class": "PrefixTransform",
          "kwargs": {
            "prefix": "gyr1"
          }
        },
        "writers": {
          "class": "UDPWriter",
          "kwargs": {
            "port": 6224
          }
        }
      }
    }
  ]
}
```

We could then call the code

```
listener = ListenerFromLoggerConfigFile('gyr1_config.yaml')
listener.run()
```
or execute

```
logger/listener/listen.py --config_file gyr1_config.yaml
```
from the command line to read the file and assemble the components as specified. Please see [OpenRVDAS Configuration Files](configuration_files.md) for more information on the syntax and use of configuration files.

Note that not all implemented Reader, Transform and Writer components are recognized by ListenerFromLoggerConfig; please see the headers of [logger/listener/listen.py](../logger/listener/listen.py) for details.

## Components

Below, we list and briefly describe (most of) the currently-implemented Reader, Transform and Writer components. The code itself is generally well documented, and should provide more details for the interested.

### Readers

#### [SerialReader](../logger/readers/serial_reader.py)
  ```
  SerialReader(port, baudrate=9600, max_bytes=None ...)
  ```
  Instances read from the specified serial port. If max\_bytes is not specified, record delimiter is a newline, and one record is returned per read() call. Otherwise a maximum of max\_bytes are read, and returned. Can take any of the optional parameters implemented by pyserial for serial port configuration.

#### [NetworkReader](../logger/readers/network_reader.py)
  ```
  NetworkReader(network, buffer_size=BUFFER_SIZE)
  ``` 
  Instances open a network socket, where network is assumed to be a host:port pair. If host is omitted (':port'), a NetworkReader attempts to read UDP records on the specified port.

#### [TextFileReader](../logger/readers/text_file_reader.py)
  ```
  TextFileReader(file_spec=None, tail=False,
                 refresh_file_spec=False,
                 retry_interval=0.1, interval=0)
  ```
  Instances open files matching a (possibly wildcarded) file\_spec in order and read sequential text lines from it/them. Returns EOF when last record has been returned, unless tail=True, in which case a read() call will block and retry every retry\_interval seconds to see if new records have arrived. If refresh\_file\_spec=True, it will also re-glob the file\_spec to see if new matching files have arrived that can be read. If interval is non-zero, read() calls will sleep as appropriate in an attempt to return records as close to the specified interval as it can.

#### [LogfileReader](../logger/readers/logfile_reader.py)
  ```
  LogfileReader(filebase=None, tail=False,
                refresh_file_spec=False, retry_interval=0.1,
                interval=0, use_timestamps=False,
                date_format=timestamp.DATE_FORMAT)
  ```
  Instances open files matching the (possibly wildcarded) filebase in alphanumeric order and read records out in sequential order, sleeping as necessary to deliver records every interval seconds. They expect records to be timestamp-prefixed and, if use\_timestamps is True, will try to deliver the records at intervals corresponding to the timestamp differences on the respective records.

#### [ComposedReader](../logger/readers/composed_reader.py)
  ```
  ComposedReader(readers, transforms=[], check_format=False)
  ```
  Initialized with a list of readers (or a single reader) and zero or more transforms. On read(), call all of the readers in parallel, then pass their received records through all the transforms in series. If check\_format is True, perform (rudimentary) checks to ensure that the record input/output formats of the readers and transforms are compatible.

#### [TimeoutReader](../logger/readers/timeout_reader.py)
  ```
  TimeoutReader(reader, timeout, message=None)
  ```
  Takes as its arguments a client reader instance (such as a NetworkReader), a timeout interval, a timeout and optional message. When its read() method is called, it iteratively calls its passed reader\'s read() method, discarding the received output. It only returns if/when the client reader fails to return a record within timeout seconds, in which case it returns either the passed timeout message or a default one warning that no records have been received within the specified timeout.

### Writers

#### [NetworkWriter](../logger/writers/network_writer.py)
  ```
  NetworkWriter(network, num_retry=2)
  ```
  Write received records to the specified network socket, where network is assumed to be a host:port pair. If host is omitted (':port'), a NetworkReader attempts to write UDP records to the specified port. The num\_retry parameter indicates (unsurprisingly) how many times the writer should retry if the initial attempt to write fails.

#### [TextFileWriter](../logger/writers/text_file_writer.py)
  ```
  TextFileWriter(filename=None, flush=True, truncate=False)
  ```
  Open and write received records to the specified filename. If flush is True, flush after each write. If truncate is True, truncate file prior to initial write.

#### [LogfileWriter](../logger/writers/logfile_writer.py)
  ```
  LogfileWriter(self, filebase=None, flush=True,
                time_format=timestamp.TIME_FORMAT,
                date_format=timestamp.DATE_FORMAT)
  ```
  Expect timestamped text records, and write them to a file named filebase-\<date\>. When date of records rolls over, open a new file corresponding to the new date.

#### [EmailWriter](../logger/writers/email_writer.py)
  ```
  EmailWriter(to, sender=None, subject=None, max_freq=3*60)
  ```
  Instantiate with a 'to' email address to which messages should be sent. When a record is received, compose and send an email message to the to address, from sender. If not specified at initialization, the subject line will be the initial characters of the passed record. If messages are received fewer than max_freq seconds apart, bundle them and send as a single message after max_freq seconds have elapsed.

#### [ComposedWriter](../logger/writers/composed_writer.py)
  ```
  ComposedWriter(transforms=[], writers=[], check_format=False)
  ```
  Initialized with zero or more transforms and zero or more writers. On write(), pass the record through all transforms in series, then hand the result to all writers in parallel. If check\_format is True, perform (rudimentary) checks to ensure that the record input/output formats of the transforms and writers are compatible.

### Transforms

#### [PrefixTransform](../logger/transforms/prefix_transform.py)
  ```
  PrefixTransform(prefix, sep=' ')
  ```
  Accept text records and prepend the specified prefix. If sep is specified, use that to separate the prefix from the record.

#### [TimestampTransform](../logger/transforms/timestamp_transform.py)
  ```
  TimestampTransform(time_format=TIME_FORMAT)
  ```
  Accept text records and prepend the current date/time as a timestamp. Timestamp format can be be overridded by any strftime-compatible string. Default format is %Y-%m-%d:%H:%M:%S.%f

#### [SliceTransform](../logger/transforms/slice_transform.py)
  ```
  SliceTransform(fields=None, sep=' ')
  ```
  Parameter fields specifies a comma-separated list of fields and ranges of fields to be kept in the incoming record. Fields are zero-indexed and correspond to Python range syntax, so  `fields=0,2,5:8,-2`  will select the first, third, sixth, seventh, and second from the last field in the record. The parameter `sep` specifies what separator should be used to split fields.

#### [RegexFilterTransform](../logger/transforms/regex_filter_transform.py)
  ```
  RegexFilterTransform(pattern, flags=0, negate=False)
  ```
  Only pass along records matching the specified regex pattern. Regex-compatible flags may be specified, as can a negate flag, that only passes along records *not* matching the pattern.

#### [QCFilterTransform](../logger/transforms/qc_filter_transform.py)
  ```
  QCFilterTransform(bounds, message=None)
  ```
  Accept a DASRecord and return None unless any of the record's field names match a definition in bounds and the field's value is outside the range specified in the bounds definition. The bounds parameter format is a comma-separated list of fieldname:min:max triples, where either (but not both) of min or max may be omitted for a one-sided bound. If a bound is exceeded, return a default warning message or the passed optional message string.

#### [XMLAggregatorTransform](../logger/transforms/xml_aggregator_transform.py)
  ```
  XMLAggregatorTransform()
  ```
  Accept text records that (presumably) constitute individual lines of an XML definition and return None until it has received an entire XML entity definition, at which point it returns the full definition as a single string.

#### [ParseTransform](../logger/transforms/parse_transform.py)
  ```
  ParseTransform(definition_path=record_parser.DEFAULT_DEFINITION_PATH,
                 return_json=False, return_das_record=False)
  ```
  Accept text records in "wire" format (with data\_id and timestamp prefixed) and return a Python dict of the record's field name/value pairs. Takes optional argument indicating location of device and device type definition files as a string of comma-separated paths, such as

  ```
  parser = RecordParser(definition_path='local/devices/*.yaml,/opt/openrvdas/local/devices/*.yaml')
  ```

  If ```return_json=True```, output a JSON-encoded string for the dict; if ```return_das_record=True```, return a [DASRecord](../logger/utils/das_record.py) for it. See [Parsing](parsing.md) for more details.

#### [TrueWindsTransform](../logger/transforms/true_winds_transform.py)
  ```
  TrueWindsTransform(data_id,
                     course_fields, speed_fields, heading_fields,
                     wind_dir_fields, wind_speed_fields,
                     update_on_fields=None,
                     zero_line_reference=0,
                     convert_wind_factor=1,
                     convert_speed_factor=1,
                     output_nmea=False)
  ```
  Compute true winds from aggregated values of course, speed, heading wind direction and wind speed. Instantiated with arguments specifying which data fields provide values for those variables, then accepts DASRecords and trolls through them for the those fields. When it receives an update of one of the data fields listed in update\_on\_fields, it computes true winds using the most recent values it has for all the relevant variables. If output\_nmea=True, it outputs this record in an NMEA-like format, otherwise it output a DASRecord bearing the name specified in data\_id.

  Please see [Derived Data Loggers](derived\_data.md) for more details on the general problem of creating derived data from loggers.

### Future Components

#### DatabaseReader

#### DatabaseWriter

#### ParseXMLTransform

#### AlarmWriter
