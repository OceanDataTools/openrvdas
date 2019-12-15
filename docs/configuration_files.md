# OpenRVDAS Configuration Files
© 2018-2019 David Pablo Cohn - DRAFT 2019-09-05


## Table of Contents

* [Overview](#overview)
* [Logger Configurations](#logger-configurations)
  * [Redirecting Standard Error](#redirecting-standard-error)
  * [Reader, Transform and Writer Documentation](#reader-transform-and-writer-documentation)
  * [Including Your Own Components](#including-your-own-components)
* [Cruise Definitions](#cruise-definitions)
  * [Modes](#modes)

## Overview

Please see the [OpenRVDAS Introduction to Loggers](intro_to_loggers.md)
for a general introduction to loggers.

The workhorse utility of the OpenRVDAS system is the Listener class,
which can be invoked either indirectly by ```server/logger_runner.py```
or ```server/logger_manager.py``` or directly via the ```listen.py```
script. When the listen.py script is run, it can take (among other
things) a configuration file describing what Readers, Transforms and
Writers should be run together and with what parameters.

```
logger/listener/listen.py --config_file gyr_logger.yaml
```
This document describes the format and rationale behind those
configuration files.

## Logger Configurations

In the example above, the file gyr\_logger.yaml might contain the
following text:

```
readers: # A single reader in this case
- class: SerialReader
  kwargs:
    baudrate: 9600
    port: /dev/ttyr15
transforms:  # List of transforms - these will be applied in series
- class: TimestampTransform  # no kwargs needed for TimestampTransform
- class: PrefixTransform
  kwargs:
    prefix: gyr1
writers:  # List of writers - these will be called in parallel
- class: LogfileWriter
  kwargs:
    filebase: /log/current/gyr1
- class: UDPWriter
  kwargs:
    port: 6224
```

The configuration is in [YAML format](https://yaml.org/). YAML is a strict
superset of JSON, but is more concise and allows comments, so is preferred
for readability.

In this case, the configuration definition specifies the following workflow:

![Dual output configuration](images/dual_writer.png)

The definition contains three essential keys: "readers",
"transforms", and "writers" (optional keys "name", "interval" and
"check_format" are also accepted, in keeping with the arguments taken
by the Listener class constructor).

The values for these keys should be a list of dicts each dict defining
a component.

Recall that a Listener instance runs all its Readers in parallel, pipes
their output to its Transforms in series, and dispatches their resulting
output to all its Writers in parallel, as illustrated below:

![Generic listener data flow](images/generic_listener.png)

Each Reader, Transform and Writer is specified by a dict with two keys:
``class`` and ``kwargs``. Unsurprisingly, the ``class`` key specifies the
class name of the component to be instantiated, e.g. ``SerialReader`` or
``TimestampTransform``.  The ``kwargs`` key should be a dict whose key-value
pairs are the argument names and values to be used in instantiated that class.
For example, the definition above corresponds to instantiating the following
components in Python:
```
readers = [
 SerialReader(baudrate=9600, port='/dev/ttyr15')
]
transforms = [
 TimestampTransform(),  # no kwargs needed for TimestampTransform
 PrefixTransform(prefix='gyr1')
]
writers = [
  LogfileWriter(filebase='/log/current/gyr1'),
  UDPWriter(port=6224)
]
```
Arguments for which the class provides default values may be omitted if
desired.

### Redirecting Standard Error

The Listener class accepts a further (optional) special key,
``stderr_writers``, that tells the Listener where to send any
diagnostic messages. Its format is the same as that for the normal
``writers`` key.

### Reader, Transform and Writer Documentation

Machine-extracted documentation on which Reader, Transform and Writer components
are available, along with their arguments, is available in HTML format in the
[doc/html](html) directory of this project. The [README.md](html/README.md) file
in that directory explains how the documentation is generated.

### Including Your Own Components

The 'imports' section of ``listen.py`` includes most of the commonly-used Readers, Transforms and Writers, but it is straightforward to include your own without modifying the core listener code by specifying the module path in your configuration file:

```
readers:
  class: TextFileReader
  kwargs:  # initialization kwargs
    file_spec: LICENSE

transforms:
- class: MySpecialTransform
  module: local.path.to.module.file
  kwargs:
    module_param: "my special transform parameter"

writers:
  class: TextFileWriter
```

## Cruise Definitions

A full cruise definition file (such as
[NBP1406_cruise.yaml](../test/NBP1406/NBP1406_cruise.yaml)) may define
many logger configurations. They will be contained in a "configs" dict
that maps from configuration names to the configuration definitions
themselves.

```
configs:
  gyr1->off:
    name: gyr1->off  # config name; no readers/writers etc. means it's off
  gyr1->net:
    name: gyr1->net  # config name
    readers:
      class: SerialReader
      kwargs:
        baudrate: 9600
        port: /dev/ttyr15
    transforms:
      ...
    writers:
      ...
  gyr1->file/net/db:
    name: gyr1->file/net/db  # config name
    ...
  ...
```

### Modes

Typically, a vessel will have sets of logger configurations that
should all be run together: which should be running when in port, when
underway, etc.

To accommodate easy reference to these modes of operation, we include
a "mode" dictionary in our configuration file:. Each mode
definition is a dict the keys of which are logger names, and the
values are the names of the configurations that logger should be in
when the mode is selected. To illustrate:

```
# Optional cruise metadata
cruise:
  id: NBP1406
  start: "2014-06-01"  # Quoted so YAML doesn't auto-convert to a datetime
  end: "2014-07-01"

# Which configs are associated with which (abstract) logger
loggers:
  eng1:
    configs:
    - eng1->off
    - eng1->net
    - eng1->file/net/db
  gyr1:
    configs:
    - gyr1->off
    - gyr1->net
    - gyr1->file/net/db
  knud:
    configs:
    - knud->off
    - knud->net
    - knud->file/net/db
  mwx1:
    configs:
    - mwx1->off
    - mwx1->net
    - mwx1->file/net/db
  rtmp:
    configs:
    - rtmp->off
    - rtmp->net
    - rtmp->file/net/db
  s330:
    configs:
    - s330->off
    - s330->net
    - s330->file/net/db

# Definitions of the configs themselves
configs:
  gyr1->off:
    ...
  gyr1->net:
    ...
  gyr1->file/net/db:
    ...
  ...

# Which configs should be running when in which mode
modes:
  off:
    eng1: eng1->off
    gyr1: gyr1->off
    knud: knud->off
    mwx1: mwx1->off
    rtmp: rtmp->off
    s330: s330->off
  port:
    eng1: eng1->net
    gyr1: gyr1->net
    knud: knud->off
    mwx1: mwx1->net
    rtmp: rtmp->off
    s330: s330->net
  underway:
    eng1: eng1->file/net/db
    gyr1: gyr1->file/net/db
    knud: knud->file/net/db
    mwx1: mwx1->file/net/db
    rtmp: rtmp->file/net/db
    s330: s330->file/net/db
default_mode: "off"  # In quotes because 'off' is a YAML keyword
```

For accounting purposes, our convention is to include an empty
configuration in the "configs" dict to denote the configuration of a
logger that isn't running.

Note also the additional (and optional) ```default_mode``` key
in the cruise configuration. It specifies that, lacking any other
information, which mode the system should be initialized to on startup.
