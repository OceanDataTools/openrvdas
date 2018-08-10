# OpenRVDAS Components - DRAFT
© 2018 David Pablo Cohn

This document enumerates and describes current OpenRVDAS Reader, Writer
and Transform components. For background on using them, please see the
[OpenRVDAS Introduction to
Loggers](intro_to_loggers.md)
or the more hands-on [Creating Loggers (old)](https://docs.google.com/document/d/1rrfwRCgyHqZsdkFgrmk04QC1fcgZ0Kpvt2Z7LpycIok/edit)
documents.

## Readers

### SerialReader
  ```
  SerialReader(port, baudrate=9600, max_bytes=None ...)
  ```
  Instances read from the specified serial port. If max\_bytes is not specified, record delimiter is a newline, and one record is returned per read() call. Otherwise a maximum of max\_bytes are read, and returned. Can take any of the optional parameters implemented by pyserial for serial port configuration.

### NetworkReader
  ```
  NetworkReader(network, buffer_size=BUFFER_SIZE)
  ``` 
  Instances open a network socket, where network is assumed to be a host:port pair. If host is omitted (':port'), a NetworkReader attempts to read UDP records on the specified port.

### TextFileReader
  ```
  TextFileReader(file_spec=None, tail=False,
                 refresh_file_spec=False,
                 retry_interval=0.1, interval=0)
  ```
  Instances open files matching a (possibly wildcarded) file\_spec in order and read sequential text lines from it/them. Returns EOF when last record has been returned, unless tail=True, in which case a read() call will block and retry every retry\_interval seconds to see if new records have arrived. If refresh\_file\_spec=True, it will also re-glob the file\_spec to see if new matching files have arrived that can be read. If interval is non-zero, read() calls will sleep as appropriate in an attempt to return records as close to the specified interval as it can.

### LogfileReader
  ```
  LogfileReader(filebase=None, tail=False,
                refresh_file_spec=False, retry_interval=0.1,
                interval=0, use_timestamps=False,
                date_format=timestamp.DATE_FORMAT)
  ```
  Instances open files matching the (possibly wildcarded) filebase in alphanumeric order and read records out in sequential order, sleeping as necessary to deliver records every interval seconds. They expect records to be timestamp-prefixed and, if use\_timestamps is True, will try to deliver the records at intervals corresponding to the timestamp differences on the respective records.

### ComposedReader
  ```
  ComposedReader(readers, transforms=[], check_format=False)
  ```
  Initialized with a list of readers (or a single reader) and zero or more transforms. On read(), call all of the readers in parallel, then pass their received records through all the transforms in series. If check\_format is True, perform (rudimentary) checks to ensure that the record input/output formats of the readers and transforms are compatible. See the [ComposedReaders and ComposedWriters section in the Creating OpenRVDAS Loggers](https://docs.google.com/document/d/1rrfwRCgyHqZsdkFgrmk04QC1fcgZ0Kpvt2Z7LpycIok/edit#heading=h.ze5iv8bylgtz) document for details.

### TimeoutReader
  ```
  TimeoutReader(reader, timeout, message=None)
  ```
  Takes as its arguments a client reader instance (such as a NetworkReader), a timeout interval, a timeout and optional message. When its read() method is called, it iteratively calls its passed reader\'s read() method, discarding the received output. It only returns if/when the client reader fails to return a record within timeout seconds, in which case it returns either the passed timeout message or a default one warning that no records have been received within the specified timeout.

## Writers

### NetworkWriter
  ```
  NetworkWriter(network, num_retry=2)
  ```
  Write received records to the specified network socket, where network is assumed to be a host:port pair. If host is omitted (':port'), a NetworkReader attempts to write UDP records to the specified port. The num\_retry parameter indicates (unsurprisingly) how many times the writer should retry if the initial attempt to write fails.

### TextFileWriter
  ```
  TextFileWriter(filename=None, flush=True, truncate=False)
  ```
  Open and write received records to the specified filename. If flush is True, flush after each write. If truncate is True, truncate file prior to initial write.

### LogfileWriter
  ```
  LogfileWriter(self, filebase=None, flush=True,
                time_format=timestamp.TIME_FORMAT,
                date_format=timestamp.DATE_FORMAT)
  ```
  Expect timestamped text records, and write them to a file named filebase-\<date\>. When date of records rolls over, open a new file corresponding to the new date.

### EmailWriter
  ```
  EmailWriter(to, sender=None, subject=None, max_freq=3*60)
  ```
  Instantiate with a 'to' email address to which messages should be sent. When a record is received, compose and send an email message to the to address, from sender. If not specified at initialization, the subject line will be the initial characters of the passed record. If messages are received fewer than max_freq seconds apart, bundle them and send as a single message after max_freq seconds have elapsed.

### ComposedWriter
  ```
  ComposedWriter(transforms=[], writers=[], check_format=False)
  ```
  Initialized with zero or more transforms and zero or more writers. On write(), pass the record through all transforms in series, then hand the result to all writers in parallel. If check\_format is True, perform (rudimentary) checks to ensure that the record input/output formats of the transforms and writers are compatible. See the [ComposedReaders and ComposedWriters section in the Creating OpenRVDAS Loggers](https://docs.google.com/document/d/1rrfwRCgyHqZsdkFgrmk04QC1fcgZ0Kpvt2Z7LpycIok/edit#heading=h.ze5iv8bylgtz) document for details.

## Transforms

### PrefixTransform
  ```
  PrefixTransform(prefix, sep=' ')
  ```
  Accept text records and prepend the specified prefix. If sep is specified, use that to separate the prefix from the record.

### TimestampTransform
  ```
  TimestampTransform(time_format=TIME_FORMAT)
  ```
  Accept text records and prepend the current date/time as a timestamp. Timestamp format can be be overridded by any strftime-compatible string. Default format is %Y-%m-%d:%H:%M:%S.%f

### SliceTransform
  ```
  SliceTransform(fields=None, sep=' ')
  ```
  Parameter fields specifies a comma-separated list of fields and ranges of fields to be kept in the incoming record. Fields are zero-indexed and correspond to Python range syntax, so  `fields=0,2,5:8,-2`  will select the first, third, sixth, seventh, and second from the last field in the record. The parameter `sep` specifies what separator should be used to split fields.

### RegexFilterTransform
  ```
  RegexFilterTransform(pattern, flags=0, negate=False)
  ```
  Only pass along records matching the specified regex pattern. Regex-compatible flags may be specified, as can a negate flag, that only passes along records *not* matching the pattern.

### QCFilterTransform
  ```
  QCFilterTransform(bounds, message=None)
  ```
  Accept a DASRecord and return None unless any of the record's field names match a definition in bounds and the field's value is outside the range specified in the bounds definition. The bounds parameter format is a comma-separated list of fieldname:min:max triples, where either (but not both) of min or max may be omitted for a one-sided bound. If a bound is exceeded, return a default warning message or the passed optional message string.

### XMLAggregatorTransform
  ```
  XMLAggregatorTransform()
  ```
  Accept text records that (presumably) constitute individual lines of an XML definition and return None until it has received an entire XML entity definition, at which point it returns the full definition as a single string.

### ParseNMEATransform
  ```
  ParseNMEATransform(json=False,
                     message_path=nmea_parser.DEFAULT_MESSAGE_PATH,
                     sensor_path=nmea_parser.DEFAULT_SENSOR_PATH,
                     sensor_model_path=nmea_parser.DEFAULT_SENSOR_MODEL_PATH)
  ```
  Accept NMEA text records in "wire" format (with data\_id and timestamp prefixed) and return a DASRecord instance containing a dictionary of the record's field name/value pairs. If json=True, output a JSON-encoded string for the DASRecord. Takes optional arguments indicating location of sensor, sensor\_model and message definitions. If initialized with json=True, return a JSON encoding of the DASRecord rather that the Python object. See [NMEA Parsing](https://docs.google.com/document/d/1WHrORXoImrc5yULegoyN-mutmfdn4E5XtUuF7mWt_lY/edit#heading=h.3fk0rim4ow8h) for more details.

### TrueWindsTransform
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

## Future Components

### DatabaseReader

### DatabaseWriter

### ParseXMLTransform

### AlarmWriter
