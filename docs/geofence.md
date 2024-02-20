# Geofencing and Automatic Logger Control

One of the routine and error-prone tasks that the operator of a shipboard data acquisition system may have to manage is that of
changing logger configurations depending on a ship's location: starting to log from certain instruments as a ship leaves port,
and turning others on or off as it enters or leaves EEZs, or areas of special interests.

Much of this functionality can automated by combining the appropriate OpenRVDAS readers, transforms and writers to implement
geofencing and other data-dependent logger control.

## Geofencing

The [GeofenceTransform](../logger/transforms/geofence_transform.py) listens to a stream of parsed `DASRecord` records or dictionaries of name:value pairs looking for
fields that contain latitude/longitude pairs. When found, it compares them to a geofence boundary loaded at initialization
time. If the lat/lon has crossed over the boundary since the last record, it emits a predefined 'leaving_boundary_message'
or 'entering_boundary_message' as appropriate.

Pairing this with the [LoggerManagerWriter](../logger/writers/logger_manager_writer.py) provides a simple mechanism for changing cruise modes when the
boundary in question is crossed. The simple logger definition below illustrates this:
```
# Read parsed DASRecords from UDP
readers:
  class: UDPReader
  kwargs:
    port: 6224
    
# Look for lat/lon values in the DASRecords and emit appropriate commands
# when entering/leaving EEZ. Note that EEZ files in GML format can be
# downloaded from https://marineregions.org/eezsearch.php.
transforms:
  - class: GeofenceTransform
    module: loggers.transforms.geofence_transform
    kwargs:
      latitude_field_name: s330Latitude
      longitude_field_name: s330Longitude
      boundary_file_name: /tmp/eez.gml
      leaving_boundary_message: set_active_mode underway_mode
      entering_boundary_message: set_active_mode eez_mode
      
# Send the messages that we get from geofence to the LoggerManager
writers:
  - class: LoggerManagerWriter
    module: logger.writers.logger_manager_writer
    kwargs:
      database: django
      allowed_prefixes:
        - 'set_active_mode '
        - 'sleep '
```
* The **UDPReader** listens for DASRecords on UDP port 6224
* The **GeofenceTransform** receives these records, looking for latitude values named `s330Latitude` and longitudes named `s330Longitude`.
  * When it finds such a pair, it compares the lat/lon values with the boundary loaded from /tmp/eez.gml.
  * If the previous lat/lon values were inside the boundary and the current ones are outside, it emits the message `set_active_mode underway_mode`.
  * If the previous lat/lon values were _outside_ the boundary and the current ones are _inside_, it emits the message `set_active_mode eez_mode`.
  * Otherwise, it emits nothing.
* The **LoggerManagerWriter** receives any emitted messages, compares them against its list of allowed message prefixes and,
  if they are allowable, issues them as commands to the LoggerManager, switching the cruise mode between `eez_mode` and
  `underway_mode` and back, as appropriate.

### Additional GeofenceTransform parameters

Additional optional `GeofenceTransform` parameters allow offsetting the switchover point from the boundary to provide a
buffer, and limiting the lat/lon check to no more than once every N seconds, to decrease computational overhead.   
```
distance_from_boundary_in_degrees
          Optional distance from boundary to place the fence, in degrees.
          Negative means inside the boundary.
          
seconds_between_checks
          Optional number of seconds to wait between doing checks,
          to minimize computational overhead                
```

(Note that the optional parameter distance_from_boundary is in _degrees_. Computing the appropriate
value in km/nm is nontrivial and requires figuring out the right UTM projection for each
location, recomputing it for each point and switching when lat/lon moved to a new UTM
projection area, possibly resulting in discontinuities. For now, requiring offsets to be expressed in terms of degrees is
simpler and less error-prone.)

### Additional LoggerManagerWriter parameters

The `LoggerManagerWriter` needs to know how to communicate with the LoggerManager in question. This can be done by using
the `database` parameter to tell it whether to try to connect to the Django-based, SQLite-based or in-memory LoggerManager.
Alternatively, an instance of a ServerAPI may be passed in using the `api` parameter.
```
database
        String indicating which database the LoggerManager is using: django,
        sqlite, memory. Either this or 'api', but not both, must be specified.

api
        An instance of server_api.ServerAPI to use to communicate with the
        LoggerManager. Either this or 'database', but not both, must be specified.

allowed_prefixes
        Optional list of strings. If specified, only records whose prefixes match
        something in this list will be passed on as commands.
```

Multiple commands may be sent in a single record by separating them with
semicolons.

In addition to the normally-accepted LoggerManager commands, an additional
one: `sleep N` is recognized, which will pause the writer N seconds before
writing the subsequent command. This allows time, if needed, for the effects
of prior commands to settle.

## Other Data-Based Logger Control

There are ways to implement data-based control of loggers, beyond the lat/lon-specific GeofenceTransform. The
[QCFilterTransform](../logger/transforms/qc_filter_transform.py) provides a more limited, but still powerful way to
change logger state depending on the value of a specific data field:
```
# Read parsed DASRecords from UDP
readers:
  class: UDPReader
  kwargs:
    port: 6224
    
# If ship speed over ground is greater than 0.5 knots, declare us
# underway, and start logging.
transforms:
  - class: QCFilterTransform
    module: loggers.transforms.qc_filter_transform
    kwargs:
      bounds: 's330SpeedKt:0.0:0.5'
      message: set_active_mode underway_mode
      
# Send the messages that we get from geofence to the LoggerManager
writers:
  - class: LoggerManagerWriter
    module: logger.writers.logger_manager_writer
    kwargs:
      database: django
      allowed_prefixes:
        - 'set_active_mode '
        - 'sleep '
```

* The `bounds` parameter takes a string of comma-separated triplets of the form `<field_name>:<lower_bound>:<upper_bound>`
  * `<field_name>` (in this case `s330SpeedKts`) says to look for values of that field in the incoming records
  * `<lower_bound>:<upper_bound>` (in this case `0.0:0.5`), specify the "normal" range of values of this field. In this case,
     "normal" would be when the ship is moving less than 0.5 knots, or approximately at rest.
* When the tested condition is no longer met (i.e. the ship is moving), the transform will output the string specified
  in the `message` parameter: `set_active_mode underway_mode`.

This message gets passed on to the LoggerManagerWriter which, as before, will interpret it as a command and set the system into underway mode.

Note that if you also wanted the system to switch out of underway mode when the ship's speed slowed back down below a certain value, you
would need to create a second logger (or use a [ComposedWriter](../logger/writers/composed_writer.py)) using a bounds line like `s330SpeedKt:0.5:100` and an appropriate
message to switch to the desired mode.

Obviously, there is ample room for more powerful, or custom Transforms to allow more elaborate and/or precise control of logger
states. We gratefully welcome any code contributed to OpenRVDAS toward that end.
