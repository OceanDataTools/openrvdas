# Sikuliaq-Specific Code

This directory contains some quick hacks to generate logger
definitions for a cruise configuration JSON for Sikuliaq sensors. The
script sets up one logger for each instrument, each one listening for
UDP packets on the specified port.

The configuration file `skq/skq_cruise.json` defines a set of
loggers and modes (off, file, db, file/db) for loggers that read from
the UDP ports listed in skq/skq_ports.txt and write to logfiles and/or
an SQL database as specified.

The configuration file was created using the quick-and-dirty script:
```
   skq/create_skq_config.py < skq/skq_ports.txt > skq/skq_cruise.json
```

The script generates a configuration with four modes:

  - off - no loggers running
  - file - write logger data to file (currently in /tmp/log/...)
  - db - write logger data to SQL database
  - file/db - write logger data to both file and db

When used by the command line utility logger/utils/logger_manager.py,
you can specify the desired mode on the command line:

```
    logger/utils/logger_manager.py
      --config skq/skq_cruise.json
      --mode file/db
```

You can also switch between modes by typing the name of the new mode
(or "quit") on the command line while the logger_manager.py is
running.

*NOTE:* For testing, `create_skq_config.py` contains a line

```ALL_USE_SAME_PORT = False```

that lets us specify that all loggers should read from the same
port. This flag was used to create `skq/skq_cruise_6224.json`,
which specifies that all loggers should read from the same port
(:6224), but then filter input to make sure each reader only keeps
records that begin with their data id.

This allows us to test by running, e.g.
```
    logger/utils/logger_manager.py
      --config skq/skq_cruise_6224.json
      --mode file/db
      -v
```

and feeding with sample data written to a single network port:
```
    logger/listener/listen.py
      --file skq/sikuliaq.data
      --write_network :6224
      -v
```

The configuration file can also be used by the Django gui, as
described in the documentation under gui/, where in addition to
selecting between modes, one may manually start/stop/reconfigure
individual loggers as desired.

Again, recall that create_skq_config.py is a quick and dirty hack for
creating a usable config file (and as such will probably outlive us
all). But please don't expect too much out of it.

Note: The sensor message format definitions are under the local/
director in local/sensor/sikuliaq.json and
local/sensor_model/sikuliaq.json
