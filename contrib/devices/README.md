# Device definitions

By default, definitions in this directory and in
[logger/devices](../../logger/devices/) with the .yaml extension will
be read by any instantiated
[RecordParser](../../logger/utils/record_parser.py) and used to try to
parse named fields out of text records passed to the parser.

Standard device type definitions (such as NMEA 0183 sentences) are in
[logger/devices](../../logger/devices/). This directory (contrib/devices)
is for site-specific devices and contributed definitions.

Locations for additional/alternative definition files may be passed to
the RecordParser when it is instantiated.

Definitions in the files here should be YAML format, defining one of
two things: specific instances of devices that emit records ('device')
and the generic types/models of those devices ('device\_type').

## Device type definitions

A 'device\_type' definition specifies the record format emitted by
that type of device (such as a Seapath200 GPS), and a mapping from
that format to field names. It may also optionally contain metadata
about the units and descriptions of each of those fields.

```
Seapath200:
  category: "device_type"
  description: "Kongsberg Seapath200"

  format:
    GGA: "$GPGGA,{GPSTime:f},{Latitude:f},{NorS:w},{Longitude:f},{EorW:w},{FixQuality:d},{NumSats:d},{HDOP:f},{AntennaHeight:f},M,{GeoidHeight:f},M,{LastDGPSUpdate:f},{DGPSStationID:d}*{CheckSum:x}"
    HDT: "$GPHDT,{HeadingTrue:f},T*{CheckSum:x}"
    VTG: "$GPVTG,{CourseTrue:f},T,{CourseMag:f},M,{SpeedKt:f},N,{SpeedKm:f},K,{Mode:w}*{CheckSum:x}"
    PSXN20: "$PSXN,20,{HorizQual:d},{HeightQual:d},{HeadingQual:d},{RollPitchQual:d}*{CheckSum:x}"
    PSXN22: "$PSXN,22,{GyroCal:f},{GyroOffset:f}*{CheckSum:x}"
    PSXN23: "$PSXN,23,{Roll:f},{Pitch:f},{HeadingTrue:f},{Heave:f}*{CheckSum:x}"

  # Optional metadata to help make sense of the parsed values.
  fields:
    Roll:
      units: "degrees"
      description: "Roll, port side up is positive"
    Pitch:
      units: "degrees"
      description: "Roll, bow up is positive"
    HeadingTrue:
      units: "degrees"
      description: "True heading"
    Heave:
      units: "meters"
      description: "Positive is down"
    Latitude:
      units: "degrees"
      description: "Latitude in degrees; north or south depends on NorS"
    NorS:
      description: "N if Latitude value is north, S otherwise"
    Longitude:
      units: "degrees"
      description: "Longitude in degrees; east or west depends on value of EorW"
    EorW:
      description: "E if Longitude value is east, W otherwise"
    ...
```

The device\_type definition may contain other elements as well; the
only required elements are the name, the category (declaring the
definition as a device\_type), and a format specification. The format
can be a single string, a list of format strings, or a dict mapping
message type names to format strings (recommended for clarity). If
the device type only emits a single format, it may be specified as a
standalone string:

```
ADCP_OS75:
  category: "device_type"
  description: "RD Industries OS-75 Acoustic Doppler Current Profiler"
  format: "$PUHAW,UVH,{VelocityE:f},{VelocityN:f},{HeadingT:f}"

```

## Devices

A 'device' definition contains definitions pertaining to a specific
(physical) instance of a device\_type, such as the Seapath200 mounted
on the weather mast. It contains a mapping from the device\_type's
generic field names ('Latitude') to a variable name specific to the
device ('MastSeapath200Latitude'). It may also contain optional
information such as the device serial number, additional descriptive
text (such as its location) and a dict of timestamped calibrations.

```
seap:
  category: "device"
  device_type: "Seapath200"
  serial_number: "unknown"
  description: "Just another device description."

  # Map from device_type field names to names specific for this specific device.
  fields:
    Roll: "SeapRoll"
    Pitch: "SeapPitch"
    HeadingTrue: "SeapHeadingTrue"
    Heave: "SeapHeave"
    Latitude: "SeapLatitude"
    NorS: "SeapNorS"
    Longitude: "SeapLongitude"
    EorW: "SeapEorW"
    ...
```

## Format string definitions

The 'format' definition of a device_type can be tricky, and is worth
some discussion. We use the syntax described on the [PyPi parse()
documentation](https://pypi.org/project/parse/), but with some
additional options.

Recall that the format for a device_type may be a string, a list of
strings, or a dict mapping message type names to format strings. If it
is a list or dict, the formats are tried in order, and the result from
the first matching format is returned.

Each of the format strings will typically be a mix of literals and
```{FieldName:type}``` field definitions. Common types are **d**
(integers), **f** (float), **g** (generalized ints/floats), **w**
(letters, numbers and underscore), but there are a host of other types
available. See the [PyPi parse()
documentation](https://pypi.org/project/parse/) for a complete list.

For example, the Seapath200 GPS device might emit the string: 

  ```$GPVTG,214.31,T,232.1,M,9.6,N,17.8,K,A*19```

A format to parse it would be

  ```$GPVTG,{CourseTrue:f},T,{CourseMag:f},M,{SpeedKt:f},N,{SpeedKm:f},K,{Mode:w}*{CheckSum:x}```

In addition to the default match types defined in the [PyPi parse()
documentation](https://pypi.org/project/parse/), the
[RecordParser](../../logger/utils/record_parser_formats.py) defines a few
additional ones:

 - od = optional integer - may be empty
 - of = optional generalized float - may be empty
 - ow = optional sequence of letters, numbers, underscores
 - nc = any ASCII text that is not a comma

 - nlat = an NMEA-format lat/lon string (DDDMM.MMMM) which is to be parsed
        into decimal degrees.
 - nlat_dir = an NMEA-format lat/lon string (DDDMM.MMMM) followed by a
        comma and direction (N, E, W or S) which is to be parsed into
        signed decimal degrees. South and West are negative, North and
        East positive
 
This allows simplifying format definitions for devices that may or may
not have empty fields depending on how they've been
installed/configured.

On the NBP's Seapath device, for some reason, speed in Km is omitted:

  ```2014-08-01T00:00:01.931000Z $GPVTG,214.31,T,,M,9.6,N,,K,A*19```

So the default pattern would fail to match. Rather than adding in a
second format explicitly omitting the magnetic course and speed in
km/hr, we can make the various fields optional:

  ```$GPVTG,{CourseTrue:of},T,{CourseMag:of},M,{SpeedKt:of},N,{SpeedKm:of},K,{Mode:w}*{CheckSum:x}```

Note that use of 'ow' may be fraught from over/undermatching and
should be used with extreme caution.


