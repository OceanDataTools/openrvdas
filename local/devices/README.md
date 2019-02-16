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
