# NMEA Parsing - DEPRECATED
© David Pablo Cohn - (david.cohn@gmail)  
DRAFT 2019-07-20

**Please see the [Parsing](parsing.md) document that supercedes this one and the module described here.**

This document provides some introductory background on the NMEAParser of the OpenRVDAS architecture. For a more general introduction to the architecture, please refer to the [OpenRVDAS Introduction to Loggers](intro_to_loggers.md).

NMNEAParser ([logger/utils/nmea\_parser.py](../logger/utils/nmea_parser.py)), the class that takes text NMEA records and parses them into structured records with named fields and timestamps, is the messiest and - at present - most fragile part of the logger system. The better part of this is due to the fact that there are so many different NMEA formats, and some instruments that nominally produce the same type of message do so with different formats.

## Table of Contents

* [Basic Operation](#basic-operation)
* [Sensor definitions](#sensor-definitions)
* [Sensor model definitions](#sensor-model-definitions)
* [Sensor Models That Emit Multiple Messages](#sensor-models-that-emit-multiple-messages)
* [Message definitions](#message-definitions)
* [Locations of Message, Sensor and Sensor Model Definitions](#locations-of-message-sensor-and-sensor-model-definitions)

## Basic Operation

The basic operation of the parser is as follows

```
  >>> parser = NMEAParser()
  >>> record = 'knud 2017-11-04:07:00:33.174207 3.5kHz,5139.94,0,,,,1500,-39.587550,-37.472355'
  >>> parser.parse_record(record)

  {
    'data_id': 'knud',
    'message_type': '',
    'timestamp': 1509778833.174207,
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
Going from the timestamped NMEA text to the the structured record requires a few steps and definitions.

We expect the raw text records we receive to begin with a data\_id identifying the physical or virtual sensor that created the record and a timestamp (the ISO 8601-compliant YYYY-MM-DDTHH:MM:SS.mmmmZ format by default, but can be overridden in logger/utils/timestamp.py).

After stripping those off, we are left with the NMEA message itself. To parse that, we need to look up information about the sensor that produced it, in this case, 'knud'.

## Sensor definitions

Sensor definitions, like the other definitions we'll cover below, are basically YAML or JSON-encoded Python dictionaries. The sensor definition for 'knud' is as follows (found in [local/sensor/knud.yaml](../local/sensor/knud.yaml)):

```
    # data_id
    "knud": {
        "name": "knud",
        "model": "Knudsen",
        "fields": {
            "LFInUse": "KnudLFInUse",
            "LFDepth": "KnudLFDepth",
            "LFValidFlag": "KnudLFValidFlag",
            "HFInUse": "KnudHFInUse",
            "HFDepth": "KnudHFDepth",
            "HFValidFlag": "KnudHFValidFlag",
            "SoundVelocity": "KnudSoundVelocity",
            "Latitude": "KnudLatitude",
            "Longitude": "KnudLongitude"
        }
    }
```

The key is the data\_id itself, and the definition the data\_id with a physical (or virtual) device. A complete sensor definition may also include key/value pairs indicating the device's location, serial number, calibration coefficients and test history. But for the purposes of parsing, we're only interested in its model and fields definitions.

We'll get back to the  fields definitions soon, but for now, we consider the model field, which tells us that knud is a Knudsen.

## Sensor model definitions

The information we need to know about a Knudsen is encoded in the file [local/sensor\_model/Knudsen.yaml](../local/sensor_model/Knudsen.yaml):

```
  {
    "Knudsen": {
        // 3.5kHz,5139.94,0,,,,1500,-39.587550,-37.472355
        "fields": [
            ["LFInUse", "str"],
            ["LFDepth", "float"],
            ["LFValidFlag", "int"],
            ["HFInUse", "str"],
            ["HFDepth", "float"],
            ["HFValidFlag", "int"],
            ["SoundVelocity", "float"],
            ["Latitude", "float"],
            ["Longitude", "float"]
        ]
    }
  }
```
Note that the choice of file name is for convenience - the dictionary key (as above) is what determines the information associated with a sensor model.

A sensor model definition tells us, among other things, what kinds of messages that sensor can emit. Many sensors, such as our Knudsen, emit only one kind of message. In those cases, the message fields are included directly in the sensor definition, as above, as an ordered list of YAML or JSON-encoded [FieldName, format] pairs.

Standard NMEA formatting specifies that fields are separated by a comma, but some instruments use non-standard separators. The Gravimeter below illustrates use of the field\_delimiter definition, which specifies a regex (in this case one that separates on both spaces and colons) to accommodate non-standard sensors.

```
{
    "Gravimeter": {
        // 01:031284 00
        "field_delimiter": "[ :]",  // uses both spaces and colon.
        "fields": [
            ["CounterUnits", "int"],
            ["GravityValueMg", "int"],
            ["GravityError", "int"]
        ]
    }
}
```
Once it has a sensor model's fields and optional delimiter, the parser splits the message into its component values and assigns the values to the defined field names. It then returns to the sensor definition, and maps the field values to the name that they should bear when coming from the specific sensor (from [local/sensor/knud.yaml](../local/sensor/knud.yaml)):

```
              "LFInUse": "KnudLFInUse",
              "LFDepth": "KnudLFDepth",
              "LFValidFlag": "KnudLFValidFlag",
              "HFInUse": "KnudHFInUse",
              "HFDepth": "KnudHFDepth",
              "HFValidFlag": "KnudHFValidFlag",
              "SoundVelocity": "KnudSoundVelocity",
              "Latitude": "KnudLatitude",
              "Longitude": "KnudLongitude"
```
We want this two-step mapping because an installation may have multiple sensors of the same model (e.g. a TSG or GPS), and we want to map the generic name associated with a sensor model output to the physical sensor itself.

## Sensor Models That Emit Multiple Messages

So far we've only looked at sensor models that emit a single message. A sensor such as a Seapath200 emits multiple types of messages that are distinguished by the value(s) of their first field(s):

```
2017-11-04:05:12:19.990659 $GPVTG,226.69,T,,M,10.8,N,,K,A*23
2017-11-04:05:12:20.245888 $GPHDT,236.03,T*01
2017-11-04:05:12:20.501188 $PSXN,20,1,0,0,0*3A
2017-11-04:05:12:20.754583 $PSXN,22,0.44,0.81*30
```
To handle multiple message types, we encapsulate them in a "messages" definition: 

```
    "Seapath200": {
        "messages": {
            "$GPHDT": {
                "fields": {
                    ["HeadingTrue", "float"],
                    ["Heading_T", "str"]
                }
            },
            "$GPVTG": {
                "fields": {
                    ["CourseTrue", "float"],
                    ["CourseTrue_T", "str"],
                    ["CourseMag", "float"],
                    ["CourseMag_M", "str"],
                    ["SpeedKt", "float"],
                    ...
                }
            },
            ...
        }
    }
```

## Message definitions

We can allow ourselves one more level of abstraction: the $GPVTG message is output by many different GPS models. Instead of explicitly including it in every individual definition, we can place it in a separate "message" file (e.g. [local/message/gpvtg.yaml](../local/message/gpvtg.yaml)):

```
{
    "$GPVTG": {
        "fields": [
            ["CourseTrue", "float"],
            ["CourseTrue_T", "str"],
            ["CourseMag", "float"],
            ["CourseMag_M", "str"],
            ["SpeedKt", "float"],
            ["SpeedKt_N", "str"],
            ["SpeedKM", "float"],
            ["SpeedKM_K", "str"],
            ["Mode", "str"]
        ]
    }
```
Then, as many sensor models as we want can refer to it by name:

```
    "Seapath200": {
        "messages": {
            "$GPGGA": "$GPGGA",
            "$GPHDT": "$GPHDT",
            "$GPVTG": "$GPVTG",
            "$GPZDA": "$GPZDA",
            "$PSXN" : "$PSXN"
        }
    }
```
We can use a combination of message reference and inclusion in the same sensor model definition. This is handy for sensors that emit multiple messages, some in standard formats and some in non-standard formats (I'm looking at you, Trimble).

## Locations of Message, Sensor and Sensor Model Definitions

We tell a NMEAParser where to look for message, sensor and sensor\_model definitions when we instantiate it:

```
p = NMEAParser(message_path=DEFAULT_MESSAGE_PATH,
               sensor_path=DEFAULT_SENSOR_PATH,
               sensor_model_path=DEFAULT_SENSOR_MODEL_PATH)
```
where message\_path, sensor\_path and sensor\_model_path are wildcarded paths to the relevant files. The default values for each, encoded in [logger/utils/nmea\_parser.py](../logger/utils/nmea_parser.py) are

```
DEFAULT_MESSAGE_PATH = 'local/message/*.yaml'
DEFAULT_SENSOR_PATH = 'local/sensor/*.yaml'
DEFAULT_SENSOR_MODEL_PATH = 'local/sensor_model/*.yaml'
```

When using the `listen.py` script, alternate/additional definitions
may be loaded by specifying a comma-separated list of file specs with
the appropriate command line options:

```
  logger/listener/listen.py \
      --udp 6224 \
      --parse_nmea_message_path local/message/\*.yaml,test/sikuliaq/messages.yaml \
      --transform_parse_nmea \
      --write_file -
```

Recall that, as with all command line arguments with `listen.py`, the
arguments modifying `--transform_parse_nmea` must appear *before* it
on the command line.
