# Derived Data Loggers

A typical logger will receive its raw data via a serial port, or a network attached sensor. But many ships rely on derived values as well, e.g. combining relative wind speed and direction with vessel heading, course and speed to compute a true wind speed and direction.

One way of achieving this is with in-stream processes. For true winds, for example, let us assume that a system (like that on the Nathaniel B. Palmer) is configured to read raw data from serial ports and both save it locally to a logfile and broadcast it via UDP on the local network.

A true wind logger can use a configuration like the one below to listen to the network for vessel course/speed/heading values (found in s300 records) and relative wind speed and direction values (found in mwx1 records).

```
{
    "readers": {
        "class": "UDPReader",
        "kwargs": { "port": 6224 }
    },

    "transforms": [
        { "class": "ParseNMEATransform" },
        { "class": "TrueWindsTransform",
          "kwargs": {
              "data_id": "truw",
              "course_fields": "S330CourseTrue",
              "speed_fields": "S330Speed",
              "heading_fields": "S330HeadingTrue",
              "wind_dir_fields": "MwxPortRelWindDir",
              "wind_speed_fields": "MwxPortRelWindSpeed",
              "convert_speed_factor": 0.5144,  // convert kts to m/s
              "output_nmea": true
          }
        }
    ],

    "writers": {
        "class": "UDPWriter",
        "kwargs": { "port": 6224 }
    }
}
```
The configuration feeds these records into a TrueWindsTransform, which looks for relevant fields and aggregates their values to compute true wind speed and direction. It then feeds the result to a UDPWriter that rebroadcasts it back onto the network as a "synthetic" record. From the point of view of a device listening to the network, this new record is indistinguishable from records that originated from a primary logger.

Please see [logger/transforms/true\_winds\_transform.py](logger/transforms/true_winds_transform.py) and the sample configuration file [test/configs/port\_true\_winds.yaml](test/configs/port_true_winds.yaml) for an example of this implementation that can be run standalone from the command line

NOTE: If there are many derived values to be computed, it will be inefficient to have separate processes, each with its own readers, transforms and writers to compute each derived value.
