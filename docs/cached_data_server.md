# The OpenRVDAS Cached Data Server
© 2019 David Pablo Cohn - DRAFT 2019-09-15

## Table of Contents

NOTE: This document is still a partial stub broken off from the
Displays and Widgets document.

## Overview

This document describes configuration, operation and use of the
[CachedDataServer](../server/cached_data_server.md) code that is used
to feed display widgets and provide intermediate caching for derived
data transforms and others.

If you are using the default OpenRVDAS installation, you will have a
CachedDataServer running and servicing websocket connections on port
8766 (you can see how it is invoked by looking at the
``scripts/start_openrvdas.sh`` file in your installation. You may also
invoke a CachedDataServer directly from the command line. The
following command line

```
    server/cached_data_server.py \
      --udp 6225 \
      --port 8766 \
      --back_seconds 480 \
      --cleanup 60 \
      --v
```

says to

1. Listen on the UDP port specified by --network for JSON-encoded,
   timestamped, field:value pairs. See Data Input Formats, below, for
   the formats it is able to parse.

2. Store the received data in an in-memory cache, retaining the most
   recent 480 seconds for each field.

3. Wait for clients to connect to the websocket at port 8766 and serve
   them the requested data. Web clients may issue JSON-encoded
   requests of the following formats (see the definition of
   serve_requests() for insight):

## Websocket Request Types

The data server knows how to respond to a set of requests sent to it
by websocket clients:

* ```{"type":"fields"}```

   Return a list of fields for which cache has data.

* ```{'type':'describe',
    'fields':['field_1', 'field_2', 'field_3']}```

  Return a dict of metadata descriptions for each specified field. If
  'fields' is omitted, return a dict of metadata for *all* fields.

* ```{"type":"subscribe",
    "fields":{"field_1":{"seconds":50},
              "field_2":{"seconds":0},
              "field_3":{"seconds":-1}}}```

  Subscribe to updates for field\_1, field\_2 and field\_3. Allowable
  values for 'seconds':

  - 0  - provide only new values that arrive after subscription
  - -1  - provide the most recent value, and then all future new ones
  - num - provide num seconds of back data, then all future new ones

  If 'seconds' is missing, use '0' as the default.

* ```{"type":"ready"}``1

  Indicate that client is ready to receive the next set of updates
  for subscribed fields.

* ```{"type":"publish", "data":{"timestamp":1555468528.452,
                              "fields":{"field_1":"value_1",
                                        "field_2":"value_2"}}}```
                                        
  Submit new data to the cache (an alternative way to get data
  in that doesn't, e.g. have the same record size limits as a
  UDP packet).

### Via the LoggerManager

The LoggerManager may be called upon to start a CachedDataWriter
via the ``--start_data_server`` flag:
```
  server/logger_manager.py \
    --database django \
    --config test/NBP1406/NBP1406_cruise.yaml \
    --start_data_server
```
By default it will use websocket port 8766 and network UDP port 6225, but these
may be overridden with additional command line flags:
```
  server/logger_manager.py \
    --database django \
    --config test/NBP1406/NBP1406_cruise.yaml \
    --data_server_websocket 8765 \
    --data_server_udp 6226 \
    --start_data_server
```

## Feeding the CachedDataServer

As indicated above, there are several ways of feeding the server with
data to cache.

1. A process that has instantiated a CachedDataServer object can
   directly call its ``cache_record() method. See [the code
   itself](../server/cached_data_server.py) or [the pdoc-extracted
   code documentation
   page](https://htmlpreview.github.io/?https://raw.githubusercontent.com/davidpablocohn/openrvdas/master/docs/html/server/cached_data_server.html)
   for details.

2. By connecting to the server with a websocket and sending it a
   ``publish`` message, as described in [Websocket Request
   Types](websocket-request-types), above.

3. By broadcasting a JSON-encoded dict of data (described below) on
   UDP to a port that the data server is listening on, if the data
   server has been invoked with a ``--data_server_udp`` argument.

## Input Data Formats

The CachedDataServer expects to be passed records in the format of a
dict encoding optionally a source data\_id and timestamp and a
mandatory 'fields' key of field\_name: value pairs. This is the
format emitted by default by ParseTransform:

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
