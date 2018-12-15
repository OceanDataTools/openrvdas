# OpenRVDAS Display Widgets

## Overview

This document discusses writing, configuring and feeding OpenRVDAS web display widgets. Please see the [OpenRVDAS Introduction and Overview](intro_and_overview.md)
for an introduction to the OpenRVDAS system. 

![Django GUI Static Widget Example](images/django_gui_static_widget.png)

At present, there are two general types of widgets supported by the OpenRVDAS framework:

  * **"dynamic" widgets** which vary their display based on the parameters in the requested URL. At present, the only such widget supported is the Django display widget at [http://localhost:8000/widget](http://localhost:8000/widget)

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
copied over from settings.py.dist and modified as necessary for the
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

(For more information about running OpenRVDAS in a Sikuliaq-compatible installation, please see [test/sikuliaq/README.md](../test/sikuliaq/README.md).

## Connecting Data Servers to Widgets

The Django-based dynamic widget looks in [django_gui/settings.py](../django_gui/settings.py) for the value of ```WEBSOCKET_DATA_SERVER``` and attempts to connect to a data server at that address.

The static widgets rely on the file
[widgets/static/js/widgets/settings.js](static/js/widgets/settings.js)
for their definition of WEBSOCKET\_DATA\_SERVER. The settings.py file must be
copied over from
[widgets/static/js/widgets/settings.js.dist](static/js/widgets/settings.js.dist) and modified to match your installation.

In either case, the Django server should be restarted whenever either of these definitions are changed to ensure that the latest values are retrieved.

Note that, with Django, there is a further complication with the static files. For efficiency, Django can be directed to collect the static files for all its subprojects into a single directory (via the ```./manage.py collectstatic``` command). If your installation was built using one of the installation scripts, these static files have been copied into the ```openrvdas/static/``` directory, and you will need to change the definition of ```WEBSOCKET_DATA_SERVER``` in the ```settings.py``` file contained there.


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

      var widget_server = new WidgetServer(widget_list,
                                           WEBSOCKET_DATA_SERVER);
      widget_server.serve();
    </script>
  </body>
</html>
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

