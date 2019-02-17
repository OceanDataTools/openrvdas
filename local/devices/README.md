# Device definitions

Definitions in this directory should be YAML format, defining one of
two things: specific instances of devices that emit records
('device') and the generic types/models of those devices
('device_type').

A 'device_type' definition contains definitions of the record format
emitted by that type of device (such as a Seapath200 GPS), and a
mapping from that format to field names. It may also optionally
contain metadata about the units and descriptions of each of those
fields.

A 'device' definition contains definitions pertaining to a specific
(physical) instance of a device_type, such as the Seapath200 mounted
on the weather mast. It contains a mapping from the device_type's
generic field names ('Latitude') to a variable name specific to the
device ('MastSeapath200Latitude'). It may also contain information
such as the device serial number, additional descriptive text (such
as its location) and a dict of timestamped calibrations.

## Format string definitions

The 'format' definition of a device_type can be tricky, and is worth
some discussion. We use the syntax described on the [PyPi parse()
documentation](https://pypi.org/project/parse/), but with some
additional options.

First: the format for a device_type may either be a string or a list
of strings. If it is a list of strings, they are tried in order, and
the result from the first matching string is returned.

Second: in addition to the default match types defined in the [PyPi
parse() documentation](https://pypi.org/project/parse/) (d, f, w,
etc.), the [RecordParser](../../logger/utils/record_parser.py) defines
a few additional ones:

 - od = optional integer
 - of = optional generalized float
 - ow = optional sequence of letters, numbers, underscores
 - nc = any ASCII text that is not a comma
 
This allows simplifying format definitions for devices that may or may
not have empty fields depending on how they've been
installed/configured.

For example, a Seapath200 GPS device might emit the format: 

  ```$GPVTG,{CourseTrue:f},T,{CourseMag:f},M,{SpeedKt:f},N,{SpeedKm:f},K,{Mode:w}*{CheckSum:x}```

On the NBP, for some reason, speed in Km is omitted:

  ```2014-08-01T00:00:01.931000Z $GPVTG,214.31,T,,M,9.6,N,,K,A*19```

So this pattern would fail to match. Rather than adding in a second
format explicitly omitting the magnetic course and speed in km/hr, we
can make the various fields optional:

  ```$GPVTG,{CourseTrue:of},T,{CourseMag:of},M,{SpeedKt:of},N,{SpeedKm:of},K,{Mode:w}*{CheckSum:x}```

Note that use of 'ow' may be fraught from over/undermatching and
should be used with extreme caution.


