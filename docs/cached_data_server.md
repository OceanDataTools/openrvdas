# The OpenRVDAS Cached Data Server
© 2019 David Pablo Cohn - DRAFT 2019-10-04

## Table of Contents

* [Table of Contents](#table-of-contents)
* [Overview](#overview)
* [Websocket Request Types](#websocket-request-types)
* [Feeding the CachedDataServer](#feeding-the-cacheddataserver)
* [Input Data Formats](#input-data-formats)
* [Contributing](#contributing)
* [License](#license)

## Overview

This document describes configuration, operation and use of the
[CachedDataServer](../server/cached_data_server.py) code that is used
to feed display widgets and provide intermediate caching for derived
data transforms and others.

If you are using the default OpenRVDAS installation, you will have a
CachedDataServer running and servicing websocket connections on port
8766.

If you are manually running a LoggerManager, you may specify that it
start up its own CachedDataServer by specifying the ``--start_data_server``
argument on its command line. You may also invoke a standalone
CachedDataServer directly from the command line (as is done by the script
in ``scripts/start_openrvdas.sh`` in your local installation). The
following command line

```
server/cached_data_server.py \
  --udp 6225 \
  --port 8766 \
  --disk_cache /var/tmp/openrvdas/disk_cache \
  --back_seconds 3600 \
  --cleanup 60 \
  --v
```

says to

1. Listen on the UDP port specified by --network for JSON-encoded,
   timestamped, field:value pairs. See Data Input Formats, below, for
   the formats it is able to parse.

2. Store the received data in memory, retaining the most recent 3600
   seconds for each field (default is 86400 seconds = 24 hours).

   (The total number of values cached per field is also limited by the
   ``max_records`` parameter and defaults to 2880, equivalent to two
   records per minute for 24 hours. It may be overridden to "infinite"
   by setting ``--max_records=0`` on the command line.)

3. Periodically back up the in-memory cache to a disk-based cache at
   /var/tmp/openrvdas/disk_cache (By default, back up every 60
   seconds; this can be overridden with the ``--cleanup_interval``
   argument).

4. Wait for clients to connect to the websocket at port 8766 (the
   default port)and serve them the requested data. Web clients may
   issue JSON-encoded requests of the following formats (note that the
   invocation in the default OpenRVDAS installation does *not* listen
   on a UDP port, and relies on websocket connections for its data).

In the default installation, the ``supervisord`` package starts and
maintains a cached\_data\_server with the following invocation:

```
    server/cached_data_server.py --port 8766 \
        --disk_cache /var/tmp/openrvdas/disk_cache \
        --max_records 86400 -v
```

This invocation serves websocket connections on port 8766, but does
not listen on any UDP port. It maintains at most 86400 records per
field (equivalent to 24 hours of 1 Hz reporting), and maintains a disk
cache in /var/tmp/openrvdas/disk\_cache that it can call on to "warm
up" the in-memory cache if it is terminated and restarted.

Its stderr and stdout are written to
``/var/log/openrvdas/cached_data_server.std[err,out]`` respectively.

The full specification can be found in
``/etc/supervisor/conf.d/openrvdas.conf`` in Ubuntu and
``/etc/supervisord.d/openrvdas.ini`` in CentOS/Redhat.

To start/stop/restart the supervisor-maintained configuration, either
via the local webserver at
[http://openrvdas:9001](http://openrvdas:9001) (assuming your machine
is named 'openrvdas') or via the command line ``supervisorctl`` tool:

```
root@openrvdas:~# supervisorctl
cached_data_server               RUNNING   pid 5641, uptime 1:35:54
logger_manager                   RUNNING   pid 5646, uptime 1:35:53
simulate_nbp                     RUNNING   pid 5817, uptime 1:23:46

supervisor> stop cached_data_server
cached_data_server: stopped

supervisor> status
cached_data_server               STOPPED   Oct 05 04:58 AM
logger_manager                   RUNNING   pid 5646, uptime 1:36:02
simulate_nbp                     RUNNING   pid 5817, uptime 1:23:55

supervisor> start cached_data_server
cached_data_server: started

supervisor> status
cached_data_server               RUNNING   pid 15187, uptime 0:00:03
logger_manager                   RUNNING   pid 5646, uptime 1:36:09
simulate_nbp                     RUNNING   pid 5817, uptime 1:24:02

supervisor> exit
```

## Websocket Request Types

The data server knows how to respond to a set of requests sent to it
by websocket clients:

### {"type":"fields"}
  ```
  {"type":"fields"}
  ```

   Return a list of fields for which cache has data.

### {"type":"describe"}
  ```
  {'type':'describe',
    'fields':['field_1', 'field_2', 'field_3']}
  ```

  Return a dict of metadata descriptions for each specified field. If
  'fields' is omitted, return a dict of metadata for *all* fields.

### {"type":"subscribe"}
  ```
  {"type":"subscribe",
    "fields":{"field_1":{"seconds":50},
              "field_2":{"seconds":0},
              "field_3":{"seconds":-1}}}
  ```

  Subscribe to updates for field\_1, field\_2 and field\_3. Allowable
  values for 'seconds':

  - ``0``  - provide only new values that arrive after subscription
  - ``-1``  - provide the most recent value, and then all future new ones
  - ``num`` - provide num seconds of back data, then all future new ones


  If 'seconds' is missing, use '0' as the default.

  The entire specification may also have a field called 'interval',
  specifying how often server should provide updates. Will
  default to what was specified on command line with --interval
  flag (which itself defaults to 1 second intervals):

  ```
  {"type":"subscribe",
    "fields":{"field_1":{"seconds":50},
              "field_2":{"seconds":0},
              "field_3":{"seconds":-1}},
   "interval": 15
  }
  ```

  The subscription message may also have an optional 'format' field,
  which may have the value 'field\_dict' (the default) or
  'record\_list':

  ```
  {"type":"subscribe",
    "fields":{"field_1":{"seconds":50},
              "field_2":{"seconds":0},
              "field_3":{"seconds":-1}},
   "format": "record_list"
  }
  ```
  
  Field names can also use * as a wildcard, in which case all fields
  that match the pattern will be returned:
  
  ```
  {"type":"subscribe",
    "fields":{"field_*":{"seconds":50},
              "field_3":{"seconds":-1}},
   "format": "record_list"
  }
  ```

  If 'record\_list' is specified, results will be collated into a list
  of DASRecord-like dicts:

  ```
  [
    {
      'timestamp': timestamp,
      'fields': {field_name: value, field_name: value, ...}
    },
    {
      'timestamp': timestamp,
      'fields': {field_name: value, field_name: value, ...}
    },
    ...  
  ]
  ```

  If 'field\_dict' is specified (or if 'format' is left unspecified),
  results will be provided as a field dict:

  ```
  {
    'fields': {
      field_name: [(timestamp, value), (timestamp, value),...],
      field_name: [(timestamp, value), (timestamp, value),...],
      ...
    }
  }
  ```

### {"type":"ready"}
  ```
  {"type":"ready"}
  ```

  Indicate that client is ready to receive the next set of updates
  for subscribed fields.

### {"type": "publish"}
  ```
  {"type":"publish", "data":{"timestamp":1555468528.452,
                              "fields":{"field_1":"value_1",
                                        "field_2":"value_2"}}}
  ```

  Submit new data to the cache. This is the mechanism that the
  [CachedDataWriter](../logger/writers/cached_data_writer.py)
  component uses to send data to the server.

## Feeding the CachedDataServer

As indicated above, there are several ways of feeding the server with
data to cache.

1. A process that has instantiated a CachedDataServer object can
   directly call its ``cache_record()`` method. See [the code
   itself](../server/cached_data_server.py) or [the pdoc-extracted
   code documentation
   page](https://htmlpreview.github.io/?https://raw.githubusercontent.com/oceandatatools/openrvdas/master/docs/html/server/cached_data_server.html)
   for details.

2. By connecting to the server with a websocket and sending it a
   ``publish`` message, as described in [Websocket Request
   Types](websocket-request-types), above.

3. By broadcasting a JSON-encoded dict of data (described below) on
   UDP to a port that the data server is listening on, if the data
   server has been invoked with a ``--data_server_udp`` argument.
   The service start script created by the default installation does
   *not* listen to a UDP port; this can be changed by uncommenting the
   line in ``scripts/start_openrvdas.sh`` that reads:

   ``#DATA_SERVER_LISTEN_ON_UDP='--udp $DATA_SERVER_UDP_PORT'``

## Input Data Formats

Whether by UDP or websocket, the CachedDataServer expects to be
passed records in the format of a dict encoding optionally a
source data\_id and timestamp and a mandatory 'fields' key of
field\_name: value pairs. This is the format emitted by default
by ParseTransform:

   ```
   {
     "data_id": ...,    # optional
     "timestamp": ...,  # optional - use time.time() if missing
     "fields": {
       field_name: value,
       field_name: value,
       ...
     }
   }
   ```

A twist on this is that the values may either be a singleton
(int, float, string, etc) or a list. If the value is a singleton,
it is taken at face value. If it is a list, it is assumed to be a
list of (value, timestamp) tuples, in which case the top-level
timestamp, if any, is ignored.

   ```
   {
     "data_id": ...,  # optional
     "fields": {
        field_name: [(timestamp, value), (timestamp, value),...],
        field_name: [(timestamp, value), (timestamp, value),...],
        ...
     }
   }
   ```

In addition to a 'fields' field, a record may contain a 'metadata'
field. If present, the data server will look for a 'fields' dict
inside the metadata dict and add the key-value pairs there to its
cache of metadata about the fields:

   ```
   {'data_id': 's330',
    'fields': {'S330CourseMag': 244.29,
               'S330CourseTrue': 219.61,
               'S330Mode': 'A',
               'S330SpeedKm': 16.5,
               'S330SpeedKt': 8.9},
    'metadata': {'fields': {
      'S330CourseMag': {'description': 'Magnetic course',
                        'device': 's330',
                        'device_type': 'Seapath330',
                        'device_type_field': 'CourseMag',
                        'units': 'degrees'},
      'S330CourseTrue': {'description': 'True course',
                         ...}
      }
   }}
   ```

This metadata field will be generated sent at intervals by a
RecordParser (and its enclosing ParseTransform) if the parser's
``metadata_interval`` value is not None.

## Contributing

Please contact David Pablo Cohn (*david dot cohn at gmail dot com*) - to discuss
opportunities for participating in code development.

## License

This code is made available under the MIT license:

Copyright (c) 2017-2019 David Pablo Cohn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Additional Licenses
