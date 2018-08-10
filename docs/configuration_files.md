# OpenRVDAS Configuration Files
© 2018 David Pablo Cohn - DRAFT 2018-08-09


## Table of Contents

* [Overview](#overview)
* [Logger Configurations](#logger-configurations)
* [Cruise Modes](#cruise-modes)
* [Templates and Variables](#templates-and-variables)
   * [Templates](#templates)
   * [Variables](#variables)
* [Expanding Configuration Files](#expanding-configuration-files)

## Overview

Please see the [OpenRVDAS Introduction to Lggers](intro_to_loggers.md)
for a general introduction to loggers.

The workhorse utility of the OpenRVDAS system is the Listener class
which can be invoked either indirectly by manager/run\_loggers.py or
directly via the listen.py script. When the listen.py script is run, it
can take (among other things) a configuration file describing what
Readers, Transforms and Writers should be run together and with what
parameters.

```
logger/listener/listen.py --config_file gyr_logger.json
```
This document describes the format and rationale behind those
configuration files.

## Logger Configurations

In the example above, the file gyr\_logger.json might contain the
following text:

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
      // NOTE: no keyword args
    },
    {
      "class": "PrefixTransform",
      "kwargs": {
        "prefix": "gyr1"
      }
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
      "class": "NetworkWriter",
      "kwargs": {
        "network": ":6224"
      }
    }
  ]
}
```

The configuration definition is a JSON-formatted dictionary with the
following workflow:

![Dual output configuration](images/dual_writer.png)

The configuration text contains three essential keys: "readers",
"transforms", and "writers" (optional keys "name", "interval" and
"check_format" are also accepted, in keeping with the arguments taken
by the Listener class constructor).

The values for these keys may either be

1. a dict defining a component, or
1. a list of dicts, each dict defining a component

Note that if a list of components is provided for in the "readers" or
"writers", section, the listener will operate them all in parallel. If
a list of components is provided in the "transforms" section, the
listener will run them in series, as in the following diagram:

![Generic listener data flow](images/generic_listener.png)

In the case of gyr1_logger.json, the logger requires only a single
reader, so it is defined directly as a dict; the two transforms and
two writers are both defined by enclosing the pair in a list.

A full cruise definition file (such as
[sample_cruise.json](../test/configs/sample_cruise.json)) may define
many logger configurations. They will will be contained in a "configs"
dict that maps from configuration names to the configuration
definitions themselves:

```
  "configs": {
    "gyr1->off": {},
    "gyr1->net": {
      "name": "gyr1->net",
      "readers": {
        "class": "SerialReader",
        ...
      },
    "gyr1->db/file/net": {
      ...
    },
    ...
  }
```

## Cruise Modes

Typically, a vessel will have sets of logger configurations that
should all be run together: which should be running when in port, when
underway, etc.

To accommodate easy reference to these modes of operation, we include
a "mode" dictionary in our cruise definition file:. Each mode
definition is a dictm the keys of which are logger names, and the
values are the names of the configurations that logger should be in
when the mode is selected. To illustrate:

```
{
  "modes": {
    "off": {
      "knud": "knud->off",
      "gyr1": "gyr1->off",
      "mwx1": "mwx1->off",
      "s330": "s330->off",
      "eng1": "eng1->off",
      "rtmp": "rtmp->off"
    },
    "port": {
      "gyr1": "gyr1->net",
      "mwx1": "mwx1->net",
      "s330": "s330->net",
      "eng1": "eng1->net",
      "knud": "knud->off",
      "rtmp": "rtmp->off"
    },
    "underway": {
      "knud": "knud->file/net/db",
      "gyr1": "gyr1->file/net/db",
      "mwx1": "mwx1->file/net/db",
      "s330": "s330->file/net/db",
      "eng1": "eng1->file/net/db",
      "rtmp": "rtmp->file/net/db"
    }
  },
  "default_mode": "off"
}
```

For accounting purposes, our convention is to include an empty
configuration in the "configs" dict to denote the configuration of a
logger that isn't running.

```
  "configs": {
    "gyr1->off": {},
    ...
  }
```

Note also the additional (and optional) ```default_mode``` key
in the cruise configuration. It specifies that, lacking any other
information, which mode the system should be initialized to on startup.

## Templates and Variables

The configuration definition for a non-trivial logger can be
voluminous.  Multiplying that volume by the number of loggers and
configurations in a cruise, and you quickly arrive at a cruise
definition that is unreadably large and error-prone. To simplify
the creation and modification of cruise definitions, we introduce
the idea of templates and variables.

### Templates

To keep representations concise and readable, we allow components of a
configuration to be included by reference to a template. A cruise
definition may include a "templates" key with a set of definitions
like the following:

```
  "templates": {
    "GYR1_SERIAL_READER": {
      "class": "SerialReader",
      "kwargs": {
        "port": "/dev/ttyr15",
        "baudrate": 9600
      }
    },
    "GYR1_TRANSFORMS": [
      {
        "class": "TimestampTransform"
        // NOTE: no keyword args
      },
      {
      "class": "PrefixTransform",
        "kwargs": {
          "prefix": "gyr1"
        }
      }
    ],
    "GYR1_LOGFILE_WRITER": {
      "class": "LogfileWriter",
      "kwargs": {
        "filebase": "/log/current/gyr1"
      }
    },
    "GYR1_NETWORK_WRITER": {
      "class": "NetworkWriter",
      "kwargs": {
        "network": ":6224"
      }
    },
    // Logger components included by reference
    "GYR1_LOGGER": {
      "readers": "GYR1_SERIAL_READER",
      "transfoms": "GYR1_TRANSFORMS",
      "writers": ["GYR1_LOGFILE_WRITER","GYR1_NETWORK_WRITER"]
    }
  }
```
Given these definitions, the configs section may define its gyr1
logger and its siblings by reference to the appropriate template
names:

```
  "configs": {
    "gyr1": "GYR1_LOGGER",
    "mwx1": "MWX1_LOGGER",
    "s330": "S330_LOGGER"
  },
```

### Variables

We expect there to be a lot of duplication between logger components
which, for a given installation, may differ only in a few strings here
and there. Tor reduce duplication, we can use variable substitution.
Consider the dictionary below:

```
{
  "vars": {
    "%CRUISE_ID%": "NBP1700",
    "%INST%": "gyr1"
  },

  "templates": {
    ...

    "%INST%_LOGFILE_WRITER": {
      "class": "LogfileWriter",
      "kwargs": {
        "filebase": "/log/%CRUISE_ID%/docs/%INST%/raw/%CRUISE_ID%_%INST%"
      }
    },
    ...,
    "%INST%_LOGGER": {
      "readers": "%INST%_SERIAL_READER",
      "transfoms": "%INST%_TRANSFORMS",
      "writers": ["%INST%_LOGFILE_WRITER","%INST%_NETWORK_WRITER"]
    }
  },
```

Now, when a string in the "vars" section is found elsewhere in the
cruise definition, its value is substituted in. So given the above variables and templates, the following definition

```
  "modes": {
    "underway": {
      "gyr1": "%INST%_LOGGER",
    }
  }
```
would be expanded into a full definition for a gyr1 configuration that
reads from a serial port, transforms its input and writes to both the
network and a logfile.

IMPORTANT: **Template references** are only applied if the key in the
template dict matches an entire string exactly elsewhere in the
definition file. **Variable substitution** is applied as a str.replace()
operation on all strings in the definition.

To further reduce duplication, var string replacements may be lists:

```
  "vars": {
    "%CRUISE_ID%": "NBP1700",
    "%INST%": ["gyr1", "mwx1", "s330"]
  }
```
In this case, an entry is created for each of the values in the list.
When that variable appears as the key of a dict, it will result in one
new dictionary entry for each value, with

```
  "%INST%_LOGGER": {
    "readers": "%INST%_SERIAL_READER",
    "transfoms": "%INST%_TRANSFORMS",
    "writers": ["%INST%_LOGFILE_WRITER","%INST%_NETWORK_WRITER"]
  }
```
becoming

```
  "gyr1_LOGGER": {
    "readers": "gyr1_SERIAL_READER",
    "transfoms": "gyr1_TRANSFORMS",
    "writers": ["gyr1_LOGFILE_WRITER","gyr1_NETWORK_WRITER"]
  },
    "mwx1_LOGGER": {
    "readers": "mwx1_SERIAL_READER",
    "transfoms": "mwx1_TRANSFORMS",
    "writers": ["mwx1_LOGFILE_WRITER","mwx1_NETWORK_WRITER"]
  },
  "s330_LOGGER": {
    "readers": "s330_SERIAL_READER",
    "transfoms": "s330_TRANSFORMS",
    "writers": ["s330_LOGFILE_WRITER","s330_NETWORK_WRITER"]
  }
```
## Expanding Configuration Files

The logger\_manager.py script takes an "expanded" cruise configuration;
to perform the expansion that makes variable replacements and reference
swaps, we need to process a raw cruise config file through the build\_configs.py script:

```
logger/utils/build_config.py \
    --config test/configs/sample_cruise_templat.json > sample_cruise.json
```
We can then start logger\_manager.py with the expanded configuration:

```
server/logger_manager.py --config sample_cruise.json
```

Please see the sample cruise template file in
[test/configs/sample\_cruise\_template.json](../test/configs/sample_cruise_template.json)
and compiled sample cruise definition in
[test/configs/sample\_cruise.json](../test/configs/sample_cruise.json)
