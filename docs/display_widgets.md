# OpenRVDAS Display Widgets
© 2018-2019 David Pablo Cohn - DRAFT 2019-03-16

## Table of Contents

* [Overview](#overview)
* [Data Servers](#data-servers)
   * [Via a CachedDataServer](#via-a-cacheddataserver)
   * [Via a CachedDataWriter](#via-a-cacheddatawriter)
   * [Via the LoggerManager](#via-the-loggermanager)

* [Feeding the CachedDataServer](#feeding-the-cached-data-server)
* [Connecting Widgets to Data Servers](#connecting-widgets-to-data-servers)
* [Widget content](#widget-content)
   * [Supported static widgets](#supported-static-widgets)
   * [Static widget transforms](#static-widget-transforms)
* [Contributing](#contributing)
* [License](#license)
* [Additional Licenses](#additional-licenses)

## Overview

This document discusses writing, configuring and feeding OpenRVDAS web display widgets. Please see the [OpenRVDAS Introduction and Overview](intro_and_overview.md)
for an introduction to the OpenRVDAS system. 

![Django GUI Static Widget Example](images/django_gui_static_widget.png)


The above diagram illustrates three widget types in an excerpt from the "static" page defined in [widgets/static/widgets/nbp_demo.html](../widgets/static/widgets/nbp_demo.html). At present, there are two general classes of widgets supported by the OpenRVDAS framework:

  * **"dynamic" widgets** which vary their display based on the parameters in the requested URL. At present, the only such widget supported is the Django display widget at [http://localhost:8000/widget](http://localhost:8000/widget).

  * **"static" widgets** coded in HTML with fixed content and layout. These all currently live in the [widgets/static/widgets](../widgets/static/widgets) directory. The figure above is an example of a static widget demonstrating dial, line chart and text elements.
  
    These static widgets are currently configured to be served by the Django interface with the path /static/widgets/[widget_name], e.g. [http://localhost:8000/static/widgets/nbp_demo.html](http://localhost:8000/static/widgets/nbp_demo.html), if for example, there is a Django test server is running from the command ```./manage.py runserver localhost:8000```.

## Data Servers

Both kinds of widgets attempt to open a websocket connection to a data
server to request and receive the data they display. At present, there
are two ways to run data servers that will feed this need. (One used
to be able to connect to a database-backed DataServer via the
LoggerManager, but we have disabled and deprecated that functionality
to simplify code. It was pretty dodgy, anyways.)

### Via a CachedDataServer

You may invoke a standalone CachedDataServer directly from the command
line. The following invocation

```
    logger/utils/cached_data_server.py \
      --network :6225 \
      --websocket :8766 \
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

   
   ```{"type":"fields"}```
   
   Return a list of fields for which cache has data

   ```
   {"type":"subscribe",
    "fields":{"field_1":{"seconds":50},
              "field_2":{"seconds":0},
              "field_3":{"seconds":-1}}}
   ```
   Subscribe to updates for field\_1, field\_2 and field\_3. Allowable
   values for 'seconds':

     - 0  - provide only new values that arrive after subscription
     - -1  - provide the most recent value, and then all future new ones
     - num - provide num seconds of back data, then all future new ones
         
     If 'seconds' is missing, use '0' as the default.

   ```
   {"type":"ready"}
   ```
   Indicate that client is ready to receive the next set of updates
   for subscribed fields.

   ```
   {"type":"publish", "data":{"timestamp":1555468528.452,
                              "fields":{"field_1":"value_1",
                                        "field_2":"value_2"}}}
   ```
   Submit new data to the cache (an alternative way to get data
   in that doesn't, e.g. have the same record size limits as a
   UDP packet).

### Via a CachedDataWriter

The CachedDataWriter is a thin wrapper around the CachedDataServer
class. You may invoke it as part of a listen.py call:

```
    logger/listener/listen.py \
      --network :6225 \
      --write_cached_data_server :8766
```

This command line creates a CachedDataWriter that performs the same
function as the cached\_data\_server.py invocation above.

Note that the listen.py script currently provides no way to override
the default values for back_seconds (480) and cleanup (60). But a
contributor who wished could easily add the appropriate flags to the
listen.py script.

The listen.py script allows a great deal of flexibility if, for example, you wish to read and serve data from raw NMEA messages, or to read records from another source such as with a LogfileReader, DatabaseReader,
RedisReader or the like):

```
    logger/listener/listen.py \
      --network :6221,:6224 \
      --parse_definition_path local/devices/*.yaml,test/sikuliaq/devices.yaml \
      --transform_parse \
      --write_cached_data_writer :8766
```

Of course, it may be incorporated (again, within its CachedDataWriter
wrapper) into a logger via a configuration file:

```
    logger/listener/listen.py --config_file data_server_config.yaml
```

where data\_server\_config.yaml contains:

```
readers:
- class: NetworkReader
  kwargs:
    network: :6221 
- class: NetworkReader
  kwargs:
    network: :6224 

transforms:
  class: ParseNMEATransform 

writers:
  class: CachedDataWriter
  kwargs:
    websocket: :8766
    back_seconds: 480
    cleanup: 60
```

Again, this will perform the same functionality as the original call.

### Via the LoggerManager

Finally, the LoggerManager may be called upon to start a CachedDataWriter
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
    --data_server_websocket :8765 \
    --data_server_udp :6226 \
    --start_data_server
```

## Feeding the CachedDataServer

The CachedDataServer expects to be passed records in one of two formats:

1. DASRecord

2. A dict encoding optionally a source data\_id and timestamp and a
   mandatory 'fields' key of field\_name: value pairs. This is the format
   emitted by default by ParseTransform:

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
   
A twist on format (2) is that the values may either be a singleton
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

You may have noticed the "publish" request described in the previous
section. This provides a secondary way to deliver new data directly to the
CachedDataServer.

## Connecting Widgets to Data Servers

The trick with connecting a display widget or web console to a data server is telling it to what websocket it should try to connect.

The Django-based dynamic widget is coded to look in
[django_gui/settings.py](../django_gui/settings.py) for the value of
```WEBSOCKET_DATA_SERVER``` and attempts to connect to a data server
at that address.

The static widgets rely on the file
[widgets/static/js/widgets/settings.js](../static/js/widgets/settings.js)
for their definition of ```WEBSOCKET_DATA_SERVER```. The settings.py
file must be copied over from
[widgets/static/js/widgets/settings.js.dist](../static/js/widgets/settings.js.dist)
and modified to match your installation.

In either case, the Django server and web server should be restarted
whenever either of these definitions are changed to ensure that the
latest values are retrieved.

Note that, with Django, there is a further complication with the
static files. For efficiency, Django can be directed to collect the
static files for all its subprojects into a single directory (via the
```./manage.py collectstatic``` command). If your instance was built
using one of the installation scripts in the [utils/](../utils/)
directory, these static files have been copied into the
```openrvdas/static/``` directory, and you will need to change the
definition of ```WEBSOCKET_DATA_SERVER``` in the ```settings.py```
file contained there.

If you are running a data server and displaying widgets that are not
updating, a good first step is to open a Javascript console on the
browser page displaying the widget to check that the widget is
attempting to connect to the data server you think is should be.

## Widget content

The provided static widgets are intended to be pedagogical,
demonstrating how to create custom widgets that meet your
installation's specific needs.

They are:

* For use with the ```test/NBP1406/NBP1406_cruise.yaml``` configuration:
  * [nbp\_demo.html](../widgets/static/widgets/nbp_demo.html)
  * [true\_winds\_demo.html](../widgets/static/widgets/true_winds_demo.html)
  * [winch\_demo.html](../widgets/static/widgets/winch_demo.html)
  * [map\_demo.html](../widgets/static/widgets/map_demo.html)
* For use with the ```test/SKQ201822S/SKQ201822S_cruise.yaml``` configuration:
  * [skq\_bridge.html](../widgets/static/widgets/skq_bridge.html)

A simple widget might be constructed as follows

```
<!DOCTYPE HTML>
<html>
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <!-- This is where we define location of data server. -->
    <script src="/static/js/widgets/settings.js"></script>
    
    <script src="/static/js/jquery/jquery-3.1.1.min.js"></script>

    <!-- For highcharts-widget.js -->
    <script src="/static/js/highcharts/code/highstock.js"></script>
    <script src="/static/js/highcharts/code/highcharts-more.js"></script>
    <script src="/static/js/highcharts/code/modules/data.js"></script>

    <script src="/static/js/widgets/highcharts_widget.js"></script>
    <script src="/static/js/widgets/widget_server.js"></script>
  </head>
  <body>
    <div id="line-container" style="height: 400px; min-width: 310px"></div>
    Heading: <span id="heading-container"></span>,
    Speed over Ground: <span id="speed-container"></span>

    <script type="text/javascript">
      //////////////////////////////////////
      // Start of widget code
      var widget_list = [];

      //////////////////
      // A line widget
      var line_fields = {
        S330Pitch: {
          name: "Pitch",
          seconds: 30
        },
        S330Roll: {
          name: "Roll",
          seconds: 30
        }
      };
      widget_list.push(new TimelineWidget('line-container',
                                          line_fields, 'Degrees'));
      widget_list.push(
          new TextWidget('heading-container',
                         {S330HeadingTrue: {name: 'Heading (True)'}}));
      widget_list.push(
          new TextWidget('speed-container',
                         {S330SOGKt: {name: 'Speed over Ground'}}));
                         
      var widget_server = new WidgetServer(widget_list,
                                           WEBSOCKET_DATA_SERVER);
      widget_server.serve();
    </script>
  </body>
</html>
```

### Supported static widgets

The types of static widgets that are currently supported are

* ```TimelineWidget(container, field_dict, [y_label], [widget_options])``` - produces a sliding timeline, as in the above example. May include any number of fields and each field may specify the name to be displayed (via "name:"), how many seconds of "back" data should be displayed (via "seconds:"), a transform (described below) and in what color to draw the line (via "color:"). Users proficient with Highcharts may specify additional Highcharts timeline widget options to override the defaults defined in [widgets/static/js/highcharts_widget.js](../widgets/static/js/highcharts_widget.js).

* ```DialWidget(container, field_dict, [widget_options])``` - produces a dial gauge with as many dial hands as fields provided.  May include any number of fields and each field may specify the name to be displayed (via "name:"), a transform (described below) and in what color to draw the line (via "color:"). Users proficient with Highcharts may specify additional Highcharts dial widget options to override the defaults defined in [widgets/static/js/highcharts_widget.js](../widgets/static/js/highcharts_widget.js).

* ```TextWidget(container, field_dict)``` - inserts the text value of the fields in question. Field dict may specify a "separator: <str>" value to indicate what string should separate the retrieved fields, and may also specify "append: true" if new values are to be appended to prior ones rather than replacing them. As above, a transform may also be specified.

Again, we recommend looking at the sample static widgets in [widgets/static/widgets/](../widgets/static/widgets/) to better understand widget construction and available options.

### Static widget transforms

Sometimes an available value may not be in the form in which we would like to display it. The desired transformation may be a question of formatting or of mathematical manipulation. To support this, all static widgets are able to parse and apply a "transform" definition in the field dict.

For example:

```
  widget_list.push(new TextWidget('gps_lat',
                                  {S330Lat: {
                                      name: "Latitude",
                                      // Round latitude to two digits
                                      transform: function(val) {
                                        return Math.round(val*100)/10000;
                                      }
                                  }}));

  widget_list.push(new TextWidget('air_temp',
                                  { MwxAirTemp: {
                                      name: 'Air Temp',
                                      // Convert C to F
                                      transform: function(val) {
                                        return ((val*9/5) + 32) + "°F";
                                  }}));
```

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

