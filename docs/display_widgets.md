# OpenRVDAS Displays and Widgets
© 2018-2019 David Pablo Cohn - DRAFT 2019-09-15

## Table of Contents

* [CAVEAT](#caveat)
* [Overview](#overview)
* [Viewing Display Pages](#viewing-display-pages)
* [Creating New Display Pages](#creating-new-display-pages)
   * [Coding with Display Widgets](#coding-with-display-widgets)
   * [Supported Widget Types](#supported-widget-types)
   * [Widget Transforms](#widget-transforms)
   * [Debugging Widgets](#debugging-widgets)
   * [Connecting Widgets to Data Servers](#connecting-widgets-to-data-servers)
* [Creating New Widgets](#creating-new-widgets)
* [Contributing](#contributing)
* [License](#license)
* [Additional Licenses](#additional-licenses)

## CAVEAT

Much of this document is deprecated. The sections following this one
all refer to OpenRVDAS-native displays, enabled on the browser side by
either D3 or HighCharts-based widgets. For maintainability and future
expansion, we are __strongly__ recommending that users focus on InfluxDB/Grafana-based displays, as described in the document [Grafana/InfluxDB-based Displays with OpenRVDAS](grafana_displays.md).

## Overview

This document discusses writing, configuring and feeding OpenRVDAS web
displays and widgets. Please see the [OpenRVDAS Introduction and
Overview](intro_and_overview.md) for an introduction to the OpenRVDAS
system.

![OpenRVDAS Display Example](images/django_gui_static_widget.png)

The active portions of a display are composed of widgets that retrieve
and display data gathered by OpenRVDAS. The above diagram illustrates
three widget types: DialWidget, TimelineWidget and TextWidget. There is
also a MapWidget, and users can create their own widget types, as long
as they adhere to the API for communicating with the OpenRVDAS
WidgetServer code.

## Viewing Display Pages

By default, display pages are located in the OpenRVDAS display/html
directory. From there they may be opened directly from the browser as
files, or may be served by Django.

To open as a file in your browser, you would load a path like:

```
file:///opt/openrvdas/display/html/nbp_basic.html
```

Note that when opening a display page this way, the Javascript widget
code on the page will need to know where to try to connect to a data
server to receive data. That information is stored in the file
`display/js/widget/settings.py` and is, by default,
``http://localhost:8766``. This will work if you are using a standard
installation of OpenRVDAS and are using a browser on the same machine
on which the system is running. Otherwise, you will need to edit the
settings.py file to point to the machine (and port) where OpenRVDAS is
running.

Django has a mechanism for serving files, which it calls "static" to
distinguish them from those it generates on the fly. The guts of
where it looks for files to serve and what URI's it uses for them are
encoded in ``django_gui/settings.py`` which, on installation, is
created from ``django_gui/settings.py.dist``.

The files in ``display/html`` are served by Django using the path
``display``:

```
http://openrvdas/display/nbp_basic.html
```

## Creating New Display Pages

There is one wrinkle in simply coding up a new display page and adding
it to the ``display/html`` directory:

Django has a quirk in that it likes to have all its "static" files in
one place but, for architectural reasons, may have them scattered
across multiple directories. To accommodate that, Django collects the
scattered files (either via copying or symlinks) into a dedicated
directory via a utility script command:

```
python3 manage.py collectstatic --no-input --link --clear
```

This command looks in ``django_gui/settings.py`` for a ``STATIC_ROOT``
definition and uses the path there as the destination for its static
files. It then looks for a``STATICFILES_DIRS`` definition and creates
symlinks to all of the files in the specified directories to the
``STATIC_ROOT`` definition. The ``--link`` argument says to make
symlinks rather than copying the source files, and the ``--clear``
argument says to clear out/refresh all old links. (The advantage of
using ``--link`` is that there is no need to re-collect after making
changes to an existing display page).

### Coding with Display Widgets

The active, useful part of these display pages are made up of display
widgets, coded in JavaScript and located in the `display/js/widgets`
directory. As mentioned above, there are currently four types of
widgets available, but creation of new widgets is encouraged.

_**NOTE:** Two types of widgets, DialWidget and TimelineWidget,
currently use the Highcharts library. We hope to soon provide purely
open source alternatives to these, but for now, if you are using them,
you should ensure that you and your organization have the appropriate
license ([Highcharts licensing is free for academic
institutions](https://shop.highsoft.com/faq))._

A simple display page might be constructed as follows

```
<!DOCTYPE HTML>
<html>
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <!-- This is where we define location of data server. -->
    <script src="../js/widgets/settings.js"></script>
    
    <script src="../js/jquery/jquery-3.6.3.min.js"></script>

    <!-- For highcharts-widget.js -->
    <script src="../js/highcharts/code/highcharts.js"></script>
    <script src="../js/highcharts/code/highcharts-more.js"></script>
    <script src="../js/highcharts/code/modules/data.js"></script>

    <script src="../js/widgets/highcharts_widget.js"></script>
    <script src="../js/widgets/widget_server.js"></script>
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
                         {S330HeadingTrue: {
                           name: 'Heading (True)',
                           timeout_css: {
                                 5: "background-color:yellow",
                                 15: "background-color:red"
                               }
                         }}));
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

The best way to get started coding up widgets for a new display is to
look at existing displays in [display/html](../display/html). But the
basic recipe is that you create a `<div>` or a `<span>` for each
widget on a page and give it an id that is unique to the page.

```
  Heading: <span id="heading-container"></span>
```

Then in JavaScript, you create an appropriate widget, passing it the
id of the div/span in question, along with parameters telling it what
it should be displaying there.

```
  var my_widget = new TextWidget('heading-container',
                                 {S330HeadingTrue: {
                                   name: 'Heading (True)',
                                   timeout_css: {
                                     5: "background-color:yellow",
                                     15: "background-color:red"
                                   }
                                 }});
```

At the end of the JavaScript, a WidgetServer is instantiated and
passed a list of all the page's widgets:

```
  var widget_server = new WidgetServer(widget_list, WEBSOCKET_DATA_SERVER);
  widget_server.serve();
```

Note the use of variable `WEBSOCKET_DATA_SERVER`, which is defined in
the `display/js/widgets/settings.js` file we described earlier.


### Supported Widget Types

The types of static widgets that are currently supported are

* ``TimelineWidget(container, field_dict, [y_label],
  [widget_options])`` Produces a sliding timeline, as in the above
  example. May include any number of fields and each field may specify
  the name to be displayed (via "name:"), how many seconds of "back"
  data should be displayed (via "seconds:"), a transform (described
  below), and in what color to draw the line (via "color:"). Users
  proficient with Highcharts may specify additional Highcharts
  timeline widget options to override the defaults defined in
  [display/js/widgets/highcharts_widget.js](../display/js/widgets/highcharts_widget.js).

* ``DialWidget(container, field_dict, [widget_options])``
  Produces a dial gauge with as many dial hands as fields provided.
  May include any number of fields and each field may specify the name
  to be displayed (via "name:"), a transform (described below) and in
  what color to draw the line (via "color:"). Users proficient with
  Highcharts may specify additional Highcharts dial widget options to
  override the defaults defined in
  [display/js/widgets/highcharts_widget.js](../display/js/widgets/highcharts_widget.js).

* ``TextWidget(container, field_dict)`` Inserts the text value of the
  fields in question. Field dict may specify a "separator: <str>"
  value to indicate what string should separate the retrieved fields,
  and may also specify "append: true" if new values are to be appended
  to prior ones rather than replacing them. As above, a transform may
  also be specified.

  TextWidget users may also specify what styling to apply to the
  container if too much time passes between updates (via
  "timeout_css:"). Given the field specification:

  ```
    {
      S330Course: {
        name: "Course",
        timeout_css: {
          5: "background-color:yellow",
          15: "background-color:red"
        }
      }
    }

  ```
  
  the text will turn yellow if 5 seconds pass with no updated values,
  and red if 10 more seconds pass with no updated valuesIt will reset
  the div to its original styling and reset the timers when a new
  value next arrives.
  
  Defined in
  [display/js/widgets/text_widget.js](../display/js/widgets/highcharts_widget.js).
  
Again, we recommend looking at the sample pages in
[display/html/](../display/html/) to better understand widget
construction and available options.

### Widget Transforms

Sometimes an available value may not be in the form in which we would
like to display it. The desired transformation may be a question of
formatting or of mathematical manipulation. To support this, all
display widgets are able to parse and apply a "transform" definition in
the field dict.

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

### Debugging Widgets

By far, the easiest way to debug misbehaving widgets is by opening
your browser's developer console. On a Mac, using Chrome, pressing
Command-Option-J will do this. From there you will be able to see
whether you have syntax errors in your JavaScript and whether the
WidgetServer is successfully connecting to its intended data server.

### Connecting Widgets to Data Servers

The WidgetServer instantiated with a page is what feeds display data
to that page's widgets. The WidgetServer does this by opening a
websocket connection to a CachedDataServer and subscribing to the
fields specified in each of its widgets' definitions.

After syntax errors, failure to connect to a data server is the most
common problem for newly-coded widgets and pages. The trick with
connecting a display widget or web console to a data server is telling
it to what websocket it should try to connect (recall that by
convention, the WidgetServer looks for a definition of
``WEBSOCKET_DATA_SERVER`` in the file
[display/js/widgets/settings.js](../static/js/widgets/settings.js)).

If you are using the default OpenRVDAS installation, you will have a
CachedDataServer running and servicing websocket connections on port
8766. Please see the [Cached Data Server](cached_data_server.md)
document for information on configuring and using Cached Data Servers.

If you are running a data server and displaying widgets that are not
updating, a good first step is to open a Javascript console on the
browser page displaying the widget to check that the widget is
attempting to connect to the data server you think is should be.

## Creating New Widgets

OpenRVDAS is designed to support easy creation of new types of
JavaScript display widgets. Three things are required of a widget:

1. A constructor that takes the name of a div or span into which it
   will place its output. A constructor will also typically include an
   argument specifying what data fields a widget should display, along
   with any parameters for displaying them.

2. A ``fields()` method that, when called, returns a list of the names
   of field names that the widget wants data for. Typically, these
   field names will be passed in, along with other customization
   information, in the widget's constructor.

3. A ``process_message(data)`` method that accepts a dictionary 
   and uses it to draw/update whatever it is displaying in its
   div/span.

   The format of the data dictionary is the same as that delivered by
   the CachedDataServer (described in the [Cached Data
   Server](cached_data_server.md) document):
   
   ```
   {
     field_name: [(timestamp, value), (timestamp, value),...],
     field_name: [(timestamp, value), (timestamp, value),...],
     field_name: [(timestamp, value), (timestamp, value),...],
   }
   ```

We recommend you examine the widgets defined in
[display/js/widgets/](../display/js/widgets) for insight and
inspiration on the construction of new widget types.

## Contributing

Please contact David Pablo Cohn (*david dot cohn at gmail dot com*) -
to discuss opportunities for participating in code development.

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

