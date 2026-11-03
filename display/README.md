# OpenRVDAS Static Widgets

## Deprecated

**The code in this directory is deprecated.** It is no longer maintained,
and new displays should not be built on it. It is kept for historical
reasons, and because the demo pages below still work as examples of
reading live data from the CachedDataServer in a web page.

New displays should be built using InfluxDB and Grafana instead. See the
online documentation:

- [Grafana/InfluxDB-based Displays](https://www.oceandatatools.org/openrvdas-docs/grafana_displays/)
- [Grafana Live Setup](https://www.oceandatatools.org/openrvdas-docs/grafana_live/)

Please see the [README.md file in the parent directory](../README.md)
for an introduction to the OpenRVDAS system.

## Overview

This directory contains Javascript code and libraries (jQuery, D3 and
Highcharts) that connect to the CachedDataServer via websocket and
display the data they receive on a web page. It is the obligation of
the user to ensure that they have the appropriate licenses and
rights to use the code in the included libraries.

## Remaining demos

An OpenRVDAS installation serves the pages in [html/](html/) at
`/display` on the console's host, e.g. `http://<host>/display/`.

- [fields.html](html/fields.html) - a table of every field the
  CachedDataServer currently knows about, with its description, units and
  source device.
- [nbp_dashboard.html](html/nbp_dashboard.html) - a dashboard for the
  NB Palmer sample cruise, drawn with Highcharts.
- [nbp_dashboard_d3.html](html/nbp_dashboard_d3.html) - the same
  dashboard, drawn with D3.
- [nbp_demo.html](html/nbp_demo.html) - a page of example Highcharts
  widgets using NB Palmer data.

The `nbp_` pages expect data from the NBP1406 sample cruise: load
[test/NBP1406/NBP1406_cruise.yaml](../test/NBP1406/NBP1406_cruise.yaml)
in the console, with the simulated NBP1406 data running (the installer
offers to set this up). `fields.html` works with any cruise.

The pages find the CachedDataServer through `js/widgets/settings.js`,
which the installer creates from
[js/widgets/settings.js.dist](js/widgets/settings.js.dist).

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

