# OpenRVDAS Terminology:

**Device Type**
  - A make/model of sensor. A device type definition describes the expected data strings that this device type is expected to generate, how to parse them, and what to name each field (optionally includes a description and unit information).
  - Example: _Seapath330_, _Knudsen3260_.

**Device**
  - Vessel/Vehicle-specific instance of a device type, such as _seapath1_, _stbd_mast_vaisala_.
  - A device definition describes how to map the generic fields in the device type produces (_Heading_, _SpeedKts_, etc.) into names that uniquely identify the source instrument and data field (_S1Heading_, _S1SpeedKts_)
  - These unique names are used when writing values to InfluxDB and the Cached Data Server (CDS).

**Logger Module**
  - One of a number of software components that can be 'tacked together' in sequence to read, process, store and/or distribute sensor data. Modules are of one of three types:
  - **Readers** - OpenRVDAS object class for ingesting data from a data source (udp, serial, file, database, MMQT, modbus, etc). When called, a Reader returns either a record or a list of records.
  - **Transforms** - OpenRVDAS object class for modifying data from a reader or upstream transform. A transform receives records as input and outputs processed and/or filtered records.
  - **Writers** - OpenRVDAS object class for writing data records to a destination (udp, serial, file, database, etc).

**Logger Configuration**
  - An end-to-end definition logger modules that describes how to read, (optionally) transform, and write a sensor data stream. A logger configuration will include
    - one or more **Readers**. If there is more than one Reader (e.g. reading multiple UDP ports), they will read in parallel.
    - zero or more **Transforms**. Transforms are applied in series.
    - one or more **Writers**. If more than one Writer, they will write parallel.
  - A simple logger configuration might be:
    ```buildoutcfg
    knud->net+file:
      readers:
      - class: SerialReader    # read a data string from serial port /dev/ttyr01
        kwargs:
          port: /dev/ttyr01
      transforms:
      - class: TimestampTransform  # prefix the data string with a timestamp
      - class: PrefixTransform     # prefix the timestamped string with 'knud'
          kwargs:
            prefix: knud
      writers:
      - class: UDPWriter      # write the prefixed, timestamped string to UDP 6224
        kwargs:
          port: 6224
      - class: LogfileWriter  # also write the prefixed, timestamped strings to file
        kwargs:
          filebase: /data/openrvdas/knud
    ```
  
**Logger**
  - The set of logger configurations defining the different logging behaviors required for a specific sensor (e.g. `knud->off`, `knud->net`, `knud->net+file`).

**Mode / Cruise Mode**
  - Typically, a vessel will have sets of logger configurations that should all be run together: which should be running when in port, when underway, etc.
  - Modes include a list of logger configurations to run.
  ```buildoutcfg
    modes:
      'off':
        gyr1: gyr1->off
        s330: s330->off
        eng1: eng1->off
        knud: knud->off
        mwx1: mwx1->off
      port:
        gyr1: gyr1->net
        s330: s330->net
        eng1: eng1->net
        knud: knud->off
        mwx1: mwx1->net
      underway:
        gyr1: gyr1->net+file
        s330: s330->net+file
        eng1: eng1->net+file
        knud: knud->net+file
        mwx1: mwx1->net+file
  ```
**Composed Writer**
  - This is a special sub-class of the writer class that allows additional transform to be applied prior to a writer.

**kwargs**
  - This is how arguments are passed to reader, transform and writer classes. It's a Python thing.

# Additional resources:

+ OpenRVDAS official documentation: https://github.com/OceanDataTools/openrvdas/tree/master/docs
+ YAML format cheatsheet: https://lzone.de/cheat-sheet/YAML

# Adding a sensor:

## Overview:
1. Write a new device type definition
2. Add a device to the ship/rov devices file
3. Add logger configurations, loggers and mode mappings to the logger_config.template file

### 1. Take a look at a device type definition:
```
######################################
Winch:
  category: "device_type"

  # If device type can output multiple formats, include them as a
  # list. Parser will use the first one that matches the whole line.
  format:

    # $FKWNC,2020-01-26T08:50:20.915150,MASH10,-3.0,0,-5.4
    # $FKWNC,2020-01-28T00:46:45.628005,Mermac,323.0,0,-8.7
    FKWNC: "$FKWNC,{Timestamp:ti},{WinchID:w},{Tension:g},{Rate:g},{Payout:g}"
    
  ########
  # Optional metadata to help make sense of the parsed values.
  fields:
    Timestamp:
      units: ""
      description: "Internal Timestamp"
    WinchID:
      units: ""
      description: "Unique Winch Identifier"
    Tension:
      units: ""
      description: "Wire Tension"
    Rate:
      units: "m/min"
      description: "Payout Speed"
    Payout:
      units: "m"
      description: "Wire Payout"
```

The file is in YAML format.  YAML is a whitespace-aware markup language, so it is imporant that the appropriate amount of leading whitespace is in each line.  There can be more than one device type definition in a single file.

The first line of text 'Winch' is the device type name.  This is used in the devices file to map a device type to a device.

The second line of text '  category: "device_type"' declares this object as contain a device type definition.

The next section declares the expected string format types for the given device:
```
  format:

    # $FKWNC,2020-01-26T08:50:20.915150,MASH10,-3.0,0,-5.4
    # $FKWNC,2020-01-28T00:46:45.628005,Mermac,323.0,0,-8.7
    FKWNC: "$FKWNC,{Timestamp:ti},{WinchID:w},{Tension:g},{Rate:g},{Payout:g}"
```

In this example the device is expected to supply strings that look similar to:
 $FKWNC,2020-01-26T08:50:20.915150,MASH10,-3.0,0,-5.4

As shown in this example it is useful for troubleshooting to include commented out (#) examples of the expected string.

Take a closer look of the format definition:
  FKWNC: "$FKWNC,{Timestamp:ti},{WinchID:w},{Tension:g},{Rate:g},{Payout:g}"

  The FKWNC key declares that the one or more following strings are of message type "FKWNC"
  "$FKWNC,{Timestamp:ti},{WinchID:w},{Tension:g},{Rate:g},{Payout:g}" is the parsing format string.

  The parsing format string is comprised of text and field definitions (i.e. {Tension:g}).  The field definition format is comprised of an optional field name (Tension), a colon (:) and a datatype (g).  If a field name is not provided the parser will still try to match the format but will not map the parsed value to a named key.

  Here is the list of available datatypes in the parse library:

    l   = Letters (ASCII)
    w   = Letters, numbers and underscore
    W   = Not letters, numbers and underscore
    s   = Whitespace
    S   = Non-whitespace
    d   = Digits (effectively integer numbers)
    D   = Non-digit
    n   = Numbers with thousands separators (, or .)
    %   = Percentage (converted to value/100.0)
    f   = Fixed-point numbers
    F   = Decimal numbers
    e   = Floating-point numbers with exponent e.g. 1.1e-10, NAN (all case insensitive)
    g   = General number format (either d, f or e)
    b   = Binary numbers
    o   = Octal numbers
    x   = Hexadecimal numbers (lower and upper case)
    ti  = ISO 8601 format date/time e.g. 1972-01-20T10:21:36Z (“T” and “Z” optional)
    te  = RFC2822 e-mail format date/time e.g. Mon, 20 Jan 1972 10:21:36 +1000
    tg  = Global (day/month) format date/time e.g. 20/1/1972 10:21:36 AM +1:00
    ta  = US (month/day) format date/time e.g. 1/20/1972 10:21:36 PM +10:30
    tc  = ctime() format date/time e.g. Sun Sep 16 01:03:52 1973
    th  = HTTP log format date/time e.g. 21/Nov/2011:00:07:11 +0000
    ts  = Linux system log format date/time e.g. Nov 9 03:37:44
    tt  = Time e.g. 10:21:36 PM -5:30

  Additional datatype options provided by OpenRVDAS: 

    od   = optional integer
    of   = optional generalized float
    og   = optional generalized number - also handles '#VALUE!' as None
    ow   = optional sequence of letters, numbers, underscores
    os   = optional sequence of any characters - will match everything on line
    nlat = NMEA-formatted latitude or longitude, converted to decimal degrees
    nlat_dir =
           NMEA-formatted latitude or longitude followed by a comma and
           hemisphere represented by [N,E,W,S]. Converted to signed decimal
           degrees with South and West indicated as negative.
    nc   = any ASCII text that is not a comma
    ns   = any ASCII text that is not a star ('*')

  The parsing format string is passed to the python parse library which will confirm whether the incoming data string matches the parsing format string and IF it does match the parse library will return a python object with the various values mapped to the field names.

Take a closer look at the fields section:
```
  ########
  # Optional metadata to help make sense of the parsed values.
  fields:
    Timestamp:
      units: ""
      description: "Internal Timestamp"
    WinchID:
      units: ""
      description: "Unique Winch Identifier"
    Tension:
      units: ""
      description: "Wire Tension"
    Rate:
      units: "m/min"
      description: "Payout Speed"
    Payout:
      units: "m"
      description: "Wire Payout"
```

This section defined additional metadata for each of the named parsed fields.

### 2. Take a look at two device definitions:
```
devices:

  ######################################
  winch_mash10:
    category: "device"
    device_type: "Winch"
    serial_number: "unknown"
    description: ""

    fields:
      Timestamp: "Winch_Mash10_Timestamp"
      WinchID: "Winch_Mash10_WinchID"
      Tension: "Winch_Mash10_Tension"
      Rate: "Winch_Mash10_Rate"
      Payout: "Winch_Mash10_Payout"

  ######################################
  winch_mermac:
    category: "device"
    device_type: "Winch"
    serial_number: "unknown"
    description: ""

    fields:
      Timestamp: "Winch_Mermac_Timestamp"
      WinchID: "Winch_Mermac_WinchID"
      Tension: "Winch_Mermac_Tension"
      Rate: "Winch_Mermac_Rate"
      Payout: "Winch_Mermac_Payout"
```

Again this is a YAML-formatted file so the leading whitespace in each line is important.

The first line: "devices" indicates that there will be one or more device definitions to follow.

```
  ######################################
  winch_mash10:
    category: "device"
    device_type: "Winch"
    serial_number: "unknown"
    description: ""
```

Here the device object/name is declared ("winch_mash10").  It is specified that the object is a device ("category: "device"), that it is a device of type "Winch" and includes some additional information such as a description and serial number.

```
    fields:
      Timestamp: "Winch_Mash10_Timestamp"
      WinchID: "Winch_Mash10_WinchID"
      Tension: "Winch_Mash10_Tension"
      Rate: "Winch_Mash10_Rate"
      Payout: "Winch_Mash10_Payout"
```

This part of the device configuration maps the field in the device type configuration to a field number unique to the individual device.  This mapping differentiates the fields for each winch ("Winch_Mash10_Tension" vs "Winch_Mermac_Tension")

### 3. Adding a logger to the configuration template

To many this is the most confusing part of the OpenRVDAS configuration process but once the concepts are understood it does make sense.  Defining a new logger within OpenRVDAS means defining a logger configuration for each operating mode, listing all the configurations for a given logger and mapping the logger configuration to the operating modes.

#### 3.a Writing a logger configuration:

Let's start with the simplest logger configuration possible.  In this example all that's being defined is an empty config that specifies what each logger should do when it's turned off.
```
configs:
  winch_mash10->off:
    name: winch_mash10->off

  winch_mermac->off:
    name: winch_mermac->off
```

All logger configurations are under the "config" section of the logger_config.yaml file, the master configuration file for OpenRVDAS.  In the example there are 2 logger configurations, one for the MASH10 winch and one for the Mermac winch.

In this next example there are logger configs that tell OpenRVDAS how to log the winch data from a UDP port, timestamp the incoming data, parse the data using the device and device type configs and finally write the data to OpenRVDAS's internal Cached Data Server (CDS) and InfluxDB: 

```
  winch_mash10->influx:
    name: winch_mash10->influx
    readers:
    - class: UDPReader
      kwargs:
        port: 10040
    transforms:
    - class: TimestampTransform
    - class: PrefixTransform
      kwargs:
        prefix: 'winch_mash10'
    - class: ParseTransform
      kwargs:
        definition_path: local/soi/ship_devices.yaml
    writers:
    - class: CachedDataWriter
      kwargs:
        data_server: localhost:8766
    - class: InfluxDBWriter
      kwargs:
        bucket_name: openrvdas
        measurement_name: winch_mash10

  winch_mermac->influx:
    name: winch_mermac->influx
    readers:
    - class: UDPReader
      kwargs:
        port: 10041
    transforms:
    - class: TimestampTransform
    - class: PrefixTransform
      kwargs:
        prefix: 'winch_mermac'
    - class: ParseTransform
      kwargs:
        definition_path: local/soi/ship_devices.yaml
    writers:
    - class: CachedDataWriter
      kwargs:
        data_server: localhost:8766
    - class: InfluxDBWriter
      kwargs:
        bucket_name: openrvdas
        measurement_name: winch_mermac
``` 

Each of these configurations conform to the standard reader, transform, writer configuration layout.  To start, the configurations define the data source as a UDP feed ("- class: UDPReader") and pass the UDP port number as a kwarg.

Next the transforms are applied to the incoming data strings.  The first is the timestamp transform.  With no additional arguments the transform simply prefixed the incoming string with a timestamp in yyyy-mm-ddTHH:MM:SS.fffZ format separated from the actual data string with a single space character.

The second transform is the prefix transform.  This transform applies the defined prefix string in front of the {timestamp} {data} string.

The last transform is the parse transform.  This is the transform that processes the prefix, timestamp and data string into an object.  A definition_path is provided to the transform so that the transform knows where to look for information on how to process the data.

From this point on the data only exists as a data object and not as the {prefix} {timestamp} {data} string from before.  This is important to remember because any transforms/writers that happen from this point must accept a data object and NOT a string.

Finally, there are the writers.  For both of these configurations there are 2 writers each.  Both writers accept the data object created by the transform parser.  The first writer is the CachedDataWriter.  This writer writes the data to the OpenRVDAS CDS at the address specified.  The second writer writes the data to the default InfluxDB (defined in the <openrvdas_root>/database/influx/settings.py file) in the specified bucket and the specified measurement name.

Let's look at a more complicated version of the MASH10 logger that does everything in the previous example but also writes the data to file in CSV format.

```
  winch_mash10->file/influx:
    name: winch_mash10->file/influx
    readers:
    - class: UDPReader
      kwargs:
        port: 10040
    transforms:
    - class: TimestampTransform
      kwargs:
        sep: ','
    writers:
    - class: LogfileWriter
      kwargs:
        filebase: /data/openrvdas/FK220101_winch_mash10
        split_char: ','
        suffix: '.txt'
    - class: ComposedWriter
      kwargs:
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: 'winch_mash10'
        - class: ParseTransform
          kwargs:
            definition_path: local/soi/ship_devices.yaml
            record_format: '{data_id:w} {timestamp:ti},{field_string}'
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:8766
        - class: InfluxDBWriter
          kwargs:
            bucket_name: openrvdas
            measurement_name: winch_mash10
```

The reader section is the same as in the previous example.  The timestamp transform has been given an additional "sep" argument declaring that the separator between the timestamp and the data should be a comma instead of a space.

There is no prefix or parse transform at this point because we want to write the data as is ({timestamp},{data}) to file.  The first writer (LogFileWriter) takes the current string and writes it to file.  The filebase and suffix argments define how to name the file: FK220101_winch_mash10_yyyymmdd.txt.  The sep argument tells the writer that the timestamp string (which LogFileWriter expects as a prefix to the data) is separated from the data by a comma.

The next writer is a Composed Writer.  A composed writer is simply an OpenRVDAS construct that allows additional transforms to be applied before writing the data to its destination.  In this example there is the same prefix transform from the previous example but with an added record_format argument.  This is to tell the transform to expect the data in a non-standard format because of the comma between the timestamp and the data.  The CachedData and InfluxDB writers are the same as before.

With the various logger configurations defined they must all be defined in the loggers section of the configuration so that OpenRVDAS is aware of all the configurations for a given logger.  This looks like:

```
loggers:
  winch_mash10:
    configs:
      - winch_mash10->off
      - winch_mash10->influx
      - winch_mash10->file/influx
  winch_mermac:
    configs:
      - winch_mermac->off
      - winch_mermac->influx
      - winch_mermac->file/influx
```

The last part of the config is to map the logger configurations for each logger to the OpenRVDAS operating modes.  This looks like:

```
modes:
  'off':
    winch_mash10: winch_mash10->off
    winch_mermac: winch_mermac->off
  'port':
    winch_mash10: winch_mash10->influx
    winch_mermac: winch_mermac->influx
  'underway':
    winch_mash10: winch_mash10->file/influx
    winch_mermac: winch_mermac->file/influx

```

The mapping does not have to be 1:1.  The same configuration can be used for multiple modes.