# Sikuliaq-Specific Code

This directory contains some quick hacks to generate logger
definitions for a cruise configuration JSON for Sikuliaq sensors. The
script sets up one logger for each instrument, each one listening for
UDP packets on the specified port.

To run, first use this script to generate the config file:
```
   skq/create_skq_config.py < skq/skq_ports.txt > skq/skq_cruise.json
```

*NOTE:* At the moment, create_skq_config.py has a "cheater" line to
simplify testing that sets all readers to read on the same port
(:6224), but then filters input to make sure each reader only keeps
records that begin with their data id.

This allows us to test by running, e.g., the command line
run_loggers.py script:

```
    logger/utils/run_loggers.py \
      --config skq/skq_cruise.json \
      --mode file/db \
      -v
```

and feed it sample data via a single port:
```
    logger/listener/listen.py \
      --file skq/sikuliaq.data \
      --write_network :6224 \
      -v
```

For actual operation, comment out the ```port = ':6224'``` line in the
create_skq_config.py script and re-generate the skq_cruise.json file.

The script generates a configuration with four modes:

  - off - no loggers running
  - file - write logger data to file (currently in /tmp/log/...)
  - db - write logger data to SQL database
  - file/db - write logger data to both file and db

When used by the command line utility logger/utils/run_loggers.py, you can
specify the desired mode on the command line:
```
    logger/utils/run_loggers.py \
      --config skq/skq_cruise.json \
      --mode file/db
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
