# OpenRVDAS Display Widgets
© 2018 David Pablo Cohn - DRAFT 2018-12-15

## Overview

This document discusses writing, configuring and feeding OpenRVDAS web display widgets. Please see the [OpenRVDAS Introduction and Overview](intro_and_overview.md)
for an introduction to the OpenRVDAS system. 

![Django GUI Static Widget Example](images/django_gui_static_widget.png)


The above diagram illustrates three widget types in an excerpt from the "static" page defined in [widgets/static/widgets/nbp_demo.html](../widgets/static/widgets/nbp_demo.html). At present, there are two general classes of widgets supported by the OpenRVDAS framework:

  * **"dynamic" widgets** which vary their display based on the parameters in the requested URL. At present, the only such widget supported is the Django display widget at [http://localhost:8000/widget](http://localhost:8000/widget).

  * **"static" widgets** coded in HTML with fixed content and layout. These all currently live in the [widgets/static/widgets](../widgets/static/widgets) directory. The figure above is an example of a static widget demonstrating dial, line chart and text elements.
  
    These static widgets are currently configured to be served by the Django interface with the path /static/widgets/[widget_name], e.g. [http://localhost:8000/static/widgets/nbp_demo.html](http://localhost:8000/static/widgets/nbp_demo.html), if for example, there is a Django test server is running from the command ```./manage.py runserver localhost:8000```.

## Data Servers

Both kinds of widgets attempt to open a websocket connection to a data server to request and receive the data they display. At present, there are two ways to run data servers that will feed this need.

### server/logger\_manager.py

If the logger\_manager.py script is run with ```--websocket :[port]```
arguments on its command line, it will attempt to run a data server
off that websocket port.  Note that by default this server is
configured to draw the data it serves from the database defined in
[database/settings.py](../database/settings.py) (which should be
copied over from [database/settings.py.dist](../database/settings.py.dist) and modified as necessary for the
local installation).

One consequence of this default is that it will
only be able to provide data when whatever loggers it is running are
actually writing to that database (e.g., mode "file/db" in the case of the
sample configs included with this distribution).

Another consequence of using the data server associated with the
logger manager is a concentration of both bandwidth and computational
requirements on a single process and machine. For that reason, when
practical, we advocate using a standalone data server, as below.

### server/network_data\_server.py

The network\_data\_server.py script is a standalone script that listens
for UDP broadcasts of NMEA logger strings, parses them, and makes them
available via a websocket.

For the NBP, where NMEA strings are broadcast via UDP on ports 6221
and 6224, a sample invocation might be

```
    server/network_data_server.py \
      --read_network :6221,:6224 \
      --websocket :8766
```

The invocation is a bit more complicated for Sikuliaq, where each instrument communicates via its own port, and which uses sensor and sensor model definitions not included in the standard set:

```
server/network_data_server.py --websocket :8766 \
  --read_network :53100,:53104,:53105,:53106,:53107,:53108,:53110,:53111,:53112,:53114,:53116,:53117,:53119,:53121,:53122,:53123,:53124,:53125,:53126,:53127,:53128,:53129,:53130,:53131,:53134,:53135,:54000,:54001,:54109,:54124,:54130,:54131,:55005,:55006,:55007,:58989 \
  --parse_nmea_sensor_path test/sikuliaq/sensors.yaml \
  --parse_nmea_sensor_model_path test/sikuliaq/sensor_models.yaml
```

(For more information about running OpenRVDAS in a Sikuliaq-compatible installation, please see [test/sikuliaq/README.md](../test/sikuliaq/README.md).)

## Connecting Data Servers to Widgets

The Django-based dynamic widget looks in [django_gui/settings.py](../django_gui/settings.py) for the value of ```WEBSOCKET_DATA_SERVER``` and attempts to connect to a data server at that address.

The static widgets rely on the file
[widgets/static/js/widgets/settings.js](static/js/widgets/settings.js)
for their definition of ```WEBSOCKET_DATA_SERVER```. The settings.py file must be
copied over from
[widgets/static/js/widgets/settings.js.dist](static/js/widgets/settings.js.dist) and modified to match your installation.

In either case, the Django server and web server should be restarted whenever either of these definitions are changed to ensure that the latest values are retrieved.

Note that, with Django, there is a further complication with the static files. For efficiency, Django can be directed to collect the static files for all its subprojects into a single directory (via the ```./manage.py collectstatic``` command). If your instance was built using one of the installation scripts in the [utils/](../utils/) directory, these static files have been copied into the ```openrvdas/static/``` directory, and you will need to change the definition of ```WEBSOCKET_DATA_SERVER``` in the ```settings.py``` file contained there.

If you are running a data server and displaying widgets that are not updating, a good first step is to open a Javascript console on the browser page displaying the widget to check that the widget is attempting to connect to the data server you think is should be.

## Widget content

The provided static widgets are intended to be pedagogical,
demonstrating how to create custom widgets that meet your
installation's specific needs.

They are:

* For use with the ```test/nmea/NBP1406/NBP1406_cruise.yaml``` configuration:
  * [nbp\_demo.html](static/widgets/nbp_demo.html)
  * [true\_winds\_demo.html](static/widgets/true_winds_demo.html)
  * [winch\_demo.html](static/widgets/winch_demo.html)
  * [map\_demo.html](static/widgets/map_demo.html)
* For use with the ```test/nmea/SKQ201822S/SKQ201822S_cruise.yaml``` configuration:
  * [skq\_bridge.html](static/widgets/skq_bridge.html)

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

Copyright (c) 2017 David Pablo Cohn

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

