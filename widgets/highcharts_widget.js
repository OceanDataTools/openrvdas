/*******************************************************************************
Create widgets using Highcharts library code (http://highcharts.com).

See README.md for full documentation.

Sample use:

  <script src="https://code.jquery.com/jquery-3.1.1.min.js"></script>
  <script src="https://code.highcharts.com/stock/highstock.js"></script>
  <script src="https://code.highcharts.com/stock/modules/exporting.js"></script>
  <script src="https://code.highcharts.com/stock/modules/export-data.js"></script>
  <script src="Highcharts-6.1.1/code/highcharts-more.js"></script>
  <script src="Highcharts-6.1.1/code/modules/data.js"></script>

  <script src="highcharts_widgets.js"></script>
  <script src="widget_server.js"></script>

  <div id="line-container" style="height: 400px; min-width: 310px"></div>
  <div id="dial-container" style="height: 400px; min-width: 310px"></div>
  <table id=ship_table>
    <tr>
      <td>Position:</td>
      <td><span id="gps_lat_container"></span></td>
    </tr>
  </table>
  <script type="text/javascript">
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

    //////////////////
    // A dial
    var dial_fields = {
      MwxPortRelWindDir: {
        name: 'Port Relative Wind',
        color: 'red',
      },
      MwxStbdRelWindDir: {
        name: 'Stbd Relative Wind',
        color: 'green',
      }
    };
    widget_list.push(new DialWidget('dial-container', dial_fields));

    //////////////////
    // Some basic row data, both singular and compound
    var gps_lat_fields = {
      S330Lat: {
        name: "Latitude",
        transform: function(val) {
          return 'Lat ' + Math.round(val*100)/10000  + '°';
        }
      },
      S330NorS: {
        name: "N/S",
      }
    };
    widget_list.push(new RowWidget('gps_lat_container', gps_lat_fields));

    var widget_server = new WidgetServer(widget_list, 'localhost:8765');
    widget_server.serve();
  </script>


This file defines two basic widgets:
  - TimelineWidget
  - DialWidget

but it should be straightforward to implement others that can be
served by the WidgetServer. To be compatible, a widget object must
have two properties:

 - this.fields: an associative array whose keys are the names of the
       desired data fields.

 - this.process_message(message): a method that receives an associative
       array whose keys are data field names and whose values are lists
       of [timestamp, value] pairs.

********************************************************************************/


/**********************
// DialWidget definition

Create a Highcharts dial displaying one or more variables

  container - name of div on page to use for displaying widget

  fields - associative array of field_name:{options} for widget

  widget_options - an optional associative array of options to use in
      place of the DialWidget's default options. Will overwrite the default
      options on a one-by-one basis.
**********************/
function DialWidget(container, fields, widget_options={}) {
  this.fields = fields;

  // Create one series for each field
  var series = [];
  var title_list = [];
  for (var id in fields) {
    // If color isn't specified, use default sequence from Highcharts
    var color = (fields[id].color
                 || Highcharts.getOptions().colors[series.length]);
    series.push({
      id: id,
      name: fields[id].name,
      data: [0],
      dial: {
        backgroundColor: color,
        borderColor: 'black',
        borderWidth: 1,
        baseWidth: 10
      },
      color: color,
      //showInLegend:true,
      tooltip: {
        valueSuffix: ' degrees'
      }
    });
    title_list.push(fields[id].name);
  }

  var this_widget_options = {
    chart: {
      type: 'gauge'
    },
    title: {
      // Just all the field names, comma separated
      text: title_list.join(", ")
    },
    legend: {
      labelFormatter: function() {
        return '<span style="text-weight:bold;color:'
            + this.userOptions.color + '">' + this.userOptions.name + '</span>';
      },
      symbolWidth: 0
    },
    pane: {
      startAngle: 0,
      endAngle: 360,
      outerRadius: '109%'
    },
    yAxis: {
      min: 0,
      max: 360,

      minorTickInterval: 'auto',
      minorTickWidth: 1,
      minorTickLength: 10,
      minorTickPosition: 'inside',
      minorTickColor: '#666',

      tickPixelInterval: 30,
      tickWidth: 2,
      tickPosition: 'inside',
      tickLength: 10,
      tickColor: '#666',
      labels: {
          step: 2,
          rotation: 'auto'
      }
    },
    series: series
  }

  // Overwrite defaults with any values passed in as widget_options
  for (option in widget_options) {
      console.log('Replacing ' + this_widget_options[option]);
      console.log('With ' + widget_options[option]);
      this_widget_options[option] = widget_options[option];
  }
  this.chart = Highcharts.chart(container, this_widget_options);

  document.addEventListener('DOMContentLoaded', this.chart);

  // When passed a websocket server /data report, sifts through
  // fields and updates any series with matching field names.
  this.process_message = function(message) {
    // Iterate over fields we're looking for, seeing if message contains
    // updates for any of them.
    for (var field_name in this.fields) {
      if (!message[field_name]) {
        continue;
      }
      var field_series = this.chart.get(field_name);
      if (field_series === undefined) {
        continue;
      }
      var value_list = message[field_name];

      // Values are [timestamp, value] pairs. Add sequentially, inefficiently.
      for (var list_i = 0; list_i < value_list.length; list_i++) {
        var value = value_list[list_i][1];
        if (this.fields[field_name].transform) {
          value = this.fields[field_name].transform(value);
        }
        //console.log(field_name + ": " + value);

        var point = field_series.points[0];
        point.update(value);
      }
    }
  }
}

/**********************
// TimelineWidget definition

Create a Highcharts line widget displaying one or more variables

  container - name of div on page to use for displaying widget

  fields - associative array of field_name:{options} for widget

  y_label - label to use for widget's y-axis

  widget_options - an optional associative array of options to use in
      place of the TimelineWidget's default options.  Will overwrite
      the default options on a one-by-one basis.

**********************/
function TimelineWidget(container, fields, y_label='',
                        widget_options={},
                        max_points=50) {
  this.fields = fields;

  // Create one series for each field
  var series = [];
  var title_list = [];
  for (var id in fields) {
    var color = (fields[id].color
                 || Highcharts.getOptions().colors[series.length]);
    series.push({
      id: id,
      name: fields[id].name,
      color: color,
      data: []
    });
    title_list.push(fields[id].name);
  }

    this_widget_options = {
    chart: {
        type: 'spline'
    },
    title: {
        // Just all the field names, comma separated
        text: title_list.join(", ")
    },
    xAxis: {
        type: 'datetime',
        tickPixelInterval: 150,
        maxZoom: 20 * 1000
    },
    yAxis: {
        minPadding: 0.2,
        maxPadding: 0.2,
        title: {
            text: y_label,
        }
    },
    series: series
  }

  // Overwrite any defaults with values passed in as widget_options
  for (option in widget_options) {
      this_widget_options[option] = widget_options[option];
  }
  this.chart = Highcharts.chart(container, this_widget_options);

  document.addEventListener('DOMContentLoaded', this.chart);

  // When passed a websocket server /data report, sifts through
  // fields and updates any series with matching field names.
  this.process_message = function(message) {
    // Iterate over fields we're looking for, seeing if message contains
    // updates for any of them.
    for (var field_name in this.fields) {
      if (!message[field_name]) {
        continue;
      }
      var field_series = this.chart.get(field_name);
      if (field_series === undefined) {
        continue;
      }
      var value_list = message[field_name];
      var msecs_to_keep = 1000 * this.fields[field_name].seconds;

      // Add points sequentially, inefficiently, bumping off old points.

      for (var list_i = 0; list_i < value_list.length; list_i++) {
        // JS uses msec, so need to multiply timestamp by 1000
        var new_point = value_list[list_i];
        new_point[0] *= 1000;
        if (this.fields[field_name].transform) {
          new_point[1] = this.fields[field_name].transform(new_point[1]);
        }

        // Inefficient (and slightly buggy) way of figuring out whether
        // we should shift old points off. Buggy because we can only ever
        // shift one point off. If we start out with more than one point
        // that is too old, we'll never catch up.
        var shift =
             (shift = field_series.points.length &&
              field_series.points[0].x < new_point[0] - msecs_to_keep)
             || field_series.data.length > this.max_points;

        field_series.addPoint(new_point, true, shift);
      }
    }
  }
}

