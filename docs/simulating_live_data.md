# Simulating Live Data
© 2019 David Pablo Cohn


See [OpenRVDAS Introduction to Loggers](intro_to_loggers.md) for system
overview.

It can be very useful, during development or testing, to run using
saved log files as synthetic input, and some sample synthetic data are
included in the test/ subdirectory for that purpose. We provide a
rudimentary simulation of data from UDP and serial port sources with
the utility script `logger/utils/simulate_data.py`.

The script may either be invoked for a single data feed with command
line options, or by specifying a YAML-format configuration file that
sets up multiple feeds at once.

To invoke a single data feed:

```
   simulate_data.py --udp 6224 \
     --filebase test/NBP1406/gyr1/raw/NBP1406_gyr1-2014-08-01
```

will read timestamped lines from files matching
`test/NBP1406/gyr1/raw/NBP1406_gyr1-2014-08-01` and broadcast them via
UDP port 6224:

```
$HEHDT,087.1,T*21
$HEHDT,087.1,T*21
$HEHDT,087.1,T*21
$HEHDT,087.1,T*21
```

By default, the reader assumes that the log file record format is `{timestamp:ti} {record}`, 
but if, for example, the timestamp has a different format, or a different
separator is used between the timestamp and record, the default may be
overridden with the --record_format argument. E.g. if a comma is used
as the delimiter between timestamp and record:
```
2019-11-28T01:01:38.762221Z,$HEHDT,087.1,T*21
2019-11-28T01:01:38.953182Z,$HEHDT,087.1,T*21
```
you may specify
```
   simulate_data.py --udp 6224 \
     --filebase test/NBP1406/gyr1/raw/NBP1406_gyr1-2014-08-01 \
     --record_format '{timestamp:ti},{record}'
```

Unless `--no-loop` is specified on the command line, the system will
rewind to the beginning of all log files when it reaches the end of
its input.

Instead of `--udp`, you may also specify `--serial` (and optionally
`--baudrate`) to simulate a serial port:

```
   simulate_data.py --serial /tmp/ttyr05 \
     --filebase test/NBP1406/gyr1/raw/NBP1406_gyr1-2014-08-01
```

If `--config` is specified

```
   simulate_data.py --config test/NBP1406/simulate_NBP1406.yaml
```

the script will expect a YAML file keyed by instrument names, where
each instrument name references a dict including keys 'class' (Serial
or UDP), 'port' (e.g. 5501 or /tmp/ttyr05) and 'filebase'. It may
optionally include 'prefix', 'eol', 'timestamp' and 'time\_format'
keys:

```
############# Gyro ###############
  gyro:
    class: UDP
    timestamp: true
    prefix: gyro
    eol: \r
    port: 56332
    filebase: /data/2019-05-11/raw/GYRO

############# Fluorometer ###############
fluorometer:
  class: Serial
  port: /tmp/ttyr04
  baudrate: 9600
  filebase: /data/2019-05-11/raw/FLUOROMETER
```

Note that if class is 'Serial', it may also include the full range of
serial port options:

```
  baudrate: 9600
  bytesize: 8
  parity: N
  stopbits: 1
  timeout: false
  xonxoff: false
  rtscts: false,
  write_timeout: false
  dsrdtr: false
  inter_byte_timeout: false
  exclusive: false
```
