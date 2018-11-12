# OpenRVDAS Static Widgets

## Overview

Please see the [README.md file in the parent directory](../README.md)
for an introduction to the OpenRVDAS system. This document discusses
specifically setting up the demo static widgets in this directory.

This directory contains Javascript code and libraries (Highcharts and
Leaflet) that are able to connect to a DataServer via websocket and
display the data they receive on a web page.

The static widget directory in
[widgets/static/widgets](static/widgets) contains static demonstration
widgets that are designed to read and display data produced when the
logger manager is running the [NBP1406 test cruise
definition](../test/nmea/NBP1406/NBP1406_cruise.json). They are provided as examples of how you or whatever webserving system you embrace, should invoke the JS widget_server.

The static widgets rely on the file
[widgets/static/js/widgets/settings.js](static/js/widgets/settings.js)
for the definition of WEBSOCKET_SERVER. The settings.py file must be
copied over from
[widgets/static/js/widgets/settings.js.dist](static/js/widgets/settings.js.dist) and modified to match your installation.

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

      var widget_server = new WidgetServer(widget_list, WEBSOCKET_SERVER);
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

