# Record Parsing
© David Pablo Cohn - (david.cohn@gmail)  
DRAFT 2019-03-16

Perhaps the second most crucial task that a data acquisition system
must accomplish (after reliably storing incoming data records) is to
be able to parse those records into meaningful values that can be
displayed and manipulated to provide insight. The
[RecordParser](../logger/utils/record_parser.py) class in
([logger/utils/record\_parser.py](../logger/utils/record_parser.py)
and its associated transform in
[logger/transforms/parse\_transform.py](../logger/transforms/parse_transform.py)
provide a tool for accomplishing this.

(Note that there is also an earlier and now-deprecated module, the
[NMEAParser](../logger/utils/nmea_parser.py), whose functionality has
mostly been superceded by the RecordParser. A section at the end of
this document describes its use.)

The [RecordParser](../logger/utils/record_parser.py) class takes text
records and parses them into structured data with named fields
and timestamps.

Input:

```
seap 2014-08-01T00:00:00.814000Z $GPZDA,000000.70,01,08,2014,,*6F
seap 2014-08-01T00:00:00.814000Z $GPGGA,000000.70,2200.112071,S,01756.360200,W,1,10,0.9,1.04,M,,M,,*41
seap 2014-08-01T00:00:00.931000Z $GPVTG,213.66,T,,M,9.4,N,,K,A*1E
```

Output:

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

## Table of Contents

* [Basic Operation](#basic-operation)
   * [ParseTransform](#parsetransform)
* [Devices and device types](#devices-and-device-types)
   * [Device type definitions](#device-type-definitions)
   * [Device definitions](#device-definitions)
* [Parser output format](#parser-output-format)
* [Parser format strings](#parser-format-strings)
   * [Additional parser formats](#additional-parser-formats)

## Basic Operation

The basic operation of the parser is as follows

```
  >>> parser = RecordParser()
  >>> record = 'knud 2014-08-01T00:00:00.814000Z 3.5kHz,5139.94,0,,,,1500,-39.587550,-37.472355'
  >>> parser.parse_record(record)

  {
    'data_id': 'knud',
    'timestamp': 1406851200.814,
    'fields':{'KnudHFDepth': None,
        'KnudHFInUse': None,
        'KnudHFValidFlag': None,
        'KnudLFDepth': 5139.94,
        'KnudLFInUse': '3.5kHz',
        'KnudLFValidFlag': 0,
        'KnudLatitude': -39.58755,
        'KnudLongitude': -37.472355,
        'KnudSoundVelocity': 1500.0},
    'metadata': {}
  }
```
Going from the timestamped text to the the structured record requires a few steps and definitions.

We expect the raw text records we receive to arrive in a predefined
format, by default beginning with a data\_id identifying the physical
or virtual sensor that created the record and an ISO 8601-compliant
timestamp followed by the body of the message (This default is defined
as ```DEFAULT_RECORD_FORMAT``` in
[logger/utils/record_parser.py](../logger/utils/record_parser.py) and
can be overridden during creation of the RecordParser instance).

After stripping the data\_id and timestamp off, we are left with the
message itself. To parse that, we need to look up information about
the device that produced it, in this case, 'knud'.

### ParseTransform

The record parser is encapulated for logger use within the thin
wrapper of the
[ParseTransform](../logger/transforms/parse_transform.py) and takes
the same optional arguments as the bare RecordParser:

  ```
  transform = ParseTransform()
  output = transform.transform(record)
  ```

It can be invoked from the command line ```listen.py``` script as well:

  ```
  logger/listener/listen.py \
      --network :6224 \
      --transform_parse \
      --write_file -
  ```

When called from listen.py, the optional RecordParser initialization
parameters may be specified with additional command line arguments
(which, in the spirit of the listen.py script, must appear on the
command line **before** ```--transform_parse``` argument):

  ```
  logger/listener/listen.py \
      --network :6224 \
      --parse_definition_path "local/devices/*.yaml,/opt/openrvdas/local/devices/*.yaml" \
      --parse_to_json \
      --transform_parse \
      --write_file -
  ```

## Devices and device types

The RecordParser works with the abstraction of "device types" and
"devices." A device type might be something like a SeaPath 330 GPS, or
a Bell Aerospace BGM-3 Gravimeter. A device would be a specific
instance of some device type, like the SeaPath 330 GPS with serial
number #S330-415-AX019G installed on the bridge of the N. B. Palmer.

### Device type definitions

Every device we wish to parse data from must have an associated device
type definition. The device type definition encodes what type of
messages that device is capable of emitting. A device may put out more
than one type of message, but we expect that _any_ SeaPath 330 or Bell
Aerospace BGM-3 will put out the same types of messages as any other.

In the case of the gravimeter, we capture this by defining a message
format along with metadata describing what each of the fields in that
format represent (in YAML, below):

```
Gravimeter_BGM3:
  category: "device_type"
  description: "Bell Aerospace BGM-3"

  format: "{CounterUnits:d}:{GravityValue:d} {GravityError:d}"

  fields:
    CounterUnits:
      description: "apparently a constant 01"
    GravityValue:
      units: "Flit Count"
      description: "mgal = flit count x 4.994072552 + bias"
    GravityError:
      description: "unknown semantics"
```

In the case of the SeaPath GPS, which can output many different types
of messages, we provide a list of formats instead of a single string:

```
Seapath330:
  category: "device_type"

  # If device type can output multiple formats, include them as a
  # list. Parser will use the first one that matches the whole line.
  format:
    - "$INGGA,{GPSTime:f},{Latitude:f},{NorS:w},{Longitude:f},{EorW:w},{FixQuality:d},{NumSats:d},{HDOP:of},{AntennaHeight:of},M,{GeoidHeight:of},M,{LastDGPSUpdate:of},{DGPSStationID:od}*{CheckSum:x}"
    - "$INHDT,{HeadingTrue:f},T*{CheckSum:x}"
    - "$INVTG,{CourseTrue:of},T,{CourseMag:of},M,{SpeedKt:of},N,{SpeedKm:of},K,{Mode:w}*{CheckSum:x}"
    - "$INZDA,{GPSTime:f},{GPSDay:d},{GPSMonth:d},{GPSYear:d},{LocalHours:od},{L
    ...
```

When handed a message that it believes to come from a SeaPath 330, the
parser will try the formats in the order listed and apply the first
one that matches.

### Device definitions

In addition to device type definitions, we need to be able to specify
which physical devices we have in our system map to which device
types. We do this with device definitions, as in the YAML definition
for a device with id 's330' on the N.B. Palmer:

```
s330:
  category: "device"
  device_type: "Seapath330"
  serial_number: "unknown"
  description: "Just another device description."

  # Map from device_type field names to names specific for this
  # specific device.
  fields:
    GPSTime: "S330GPSTime"
    FixQuality: "S330FixQuality"
    NumSats: "S330NumSats"
    HDOP: "S330HDOP"
    AntennaHeight: "S330AntennaHeight"
    GeoidHeight: "S330GeoidHeight"
    LastDGPSUpdate: "S330LastDGPSUpdate"
```

The definition tells us that this is a device (rather than device
type) definition, tells us what its device type is, and gives us a
mapping from the device type's generic field names ('SpeedKt') to the
field name we will want this datum to have in our system
('S330SpeedKt').

The location of device and device type definitions a RecordParser is to use may be specified when it is instantiated, using a string containing a comma-separated list of paths:

```
parser = RecordParser(definition_path='local/devices/*.yaml,/opt/openrvdas/local/devices/*.yaml')
```

By default, it will look for definitions in
```DEFAULT_DEFINITION_PATH```, defined as ```local/devices/*.yaml```.

## Parser output format

By default, a RecordParser will output a dict with three top-level fields:
```
{'data_id': 'seap',
 'fields': { ... },
 'timestamp': 1406851200.814
}
```
(it may, in the future, also emit a 'metadata' field containing additional information).

If invoked with ```return_das_record=True``` it will return [DASRecord
objects](../logger/utils/das_record.py), and if invoked with
```return_json=True``` it will return the dict in JSON-encoded format.

## Parser format strings

The format RecordParser relies on the [PyPi parse
module](https://pypi.org/project/parse/). In brief, the format
consists of literal text that is to be matched in a string along with
interspersed "{VariableName:VariableFormat}" definitions. The variable
formats understood roughly correspond to those in Python 3's 'print'
statement:

- d: digits
- w: letters, numbers and underscores
- f: fixed point numbers
- g: general numbers

and more elaborate formats:

- ti: ISO8601 datetime
- ts: Linux format timestamp

Please consult the documentation at [https://pypi.org/project/parse/](https://pypi.org/project/parse/) for the full list.

### Additional parser formats

For all the power encoded into PyPi's parse module, the available
formats have a few limitations. Most notably, it is difficult to cope
with missing fields in a record. For example, a SeaPath 330's
GPVTG message in theory provides both true and magnetic headings, and speed in both knots and km/hour:

```
  "$GPVTG,{CourseTrue:f},T,{CourseMag:f},M,{SpeedKt:f},N,{SpeedKm:f},K,{Mode:w}*{CheckSum:x}"
```
  
In practice, some of those fields may be empty:

```
seap 2014-08-01T00:00:00.931000Z $GPVTG,213.66,T,,M,9.4,N,,K,A*1E
```
But the 'f' format does not recognize empty numbers, so the above
record will not match our format.

To cope with this, we have created a few "extra" formats, defined in
the initial section of
[logger/utils/record\_parser.py](logger/utils/record_parser.py):

 - od = optional integer
 - of = optional generalized float
 - ow = optional sequence of letters, numbers, underscores
 - nc = any ASCII text that is not a comma

Using these, the extended format string

```
  "$GPVTG,{CourseTrue:of},T,{CourseMag:of},M,{SpeedKt:of},N,{SpeedKm:of},K,{Mode:w}*{CheckSum:x}"
```
 gracefully parses the received record, parsing and converting
  fields where they are found, and ignoring those that are missing.

See 'Custom Type Conversions' in
[https://pypi.org/project/parse/](https://pypi.org/project/parse/) for
a discussion of how format types work.
