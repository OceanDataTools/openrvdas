/*******************************************************************************
Create a text widget. See README.md for full documentation.

NOTE: Much of this code is an artifact from an earlier iteration when
each widget could have multiple fields. Now we require/expect/hope
that each widget has just a single data field. If it has multiple
fields, we'll complain, but then update the innerHTML of our container
from every one of the fields in sequence.

********************************************************************************/



/*******************************************************************************
TimeoutStyler

  Class that creates a set of timers that change the styling of a div if/when
  the reset_timers() method isn't called by the time the timeouts expire.
  For example, being called with

  var ts = new TimeoutStyler(
      my_div,
      {
        5:  "background-color:yellow",
        10: "background-color:red;font-weigh:bold",
      });

  will set the div's style to "background-color:yellow" if more than five
  seconds have elapsed since ts.reset_timers() has been called. When
  reset_timers() is called, it will reset the div's style to what it was
  when the TimeoutStyler was initialized.
********************************************************************************/
function TimeoutStyler(div, timeout_styles) {
  this.div = div;
  this.styles = timeout_styles;
  this.base_style = div.style;
  
  // Internal function to set the div to the desired style
  this.set_style = function(seconds) {
    var style = this.styles[seconds]
    this.div.style = style;
  }.bind(this);

  // Set up a timer for each timeout:style entry
  this.timers = {};
  for (var seconds in this.styles) {
    this.timers[seconds] = setTimeout(this.set_style, seconds * 1000, seconds);
  }
  
  // Reset all the timers when asked
  this.reset_timers = function() {
    // First, set the div's style back to what it was at the start
    this.div.style = this.base_style;

    // Now create one timer for each timeout style
    for (var seconds in this.styles) {
      // Clear out the old timer and set up a new one
      clearTimeout(this.timers[seconds]);
      this.timers[seconds] = setTimeout(this.set_style,
                                        seconds * 1000,
                                        seconds);
    }
  }.bind(this);
}

/********************************************************************************
TextWidget

  Takes a containing div/span and a field(s) specifier and renders the text
  values corresponding to that field in the container. The invocation

    function num_to_lat_lon(val) {
      return ((val/100).toFixed(4)).padStart(9);
    }

    var w = new TextWidget('gps_lat',
                           {
                             S330Latitude: {
                               name: "Latitude",
                               transform: num_to_lat_lon,
                               timeout_css: {
                                 5: "background-color:yellow",
                                 15: "background-color:red"
                               }
                             }
                           });

  Will subscribe to the field S330Latitude. When it receives values
  for the field, it will pass it through the num_to_lat_lon() function
  to transform it, and will display it in the div/span with id
  'gps_lat'.

  If 5 seconds pass with no updated values, it will turn the div
  yellow.  If 15 seconds pass with no updated values, it will turn the
  div red. It will reset the div to its original styling and reset the
  timers when a new value next arrives.

********************************************************************************/
function TextWidget(container, fields) {
    this.fields = fields;
    this.container = container;
    this.timeout_styler = null;
  
    if (Object.keys(this.fields).length > 1) {
        console.log('Error: TextWidget should contain only one field. Found: '
                    + JSON.stringify(fields));
    }

    this.chart = function() {
        this.container_div = document.getElementById(container);
        if (!this.container_div) {
            console.log('TextWidget unable to find container div \"'
                        + container +'\"');
        }

        // See if var has any timeout styling css
        for (var field in this.fields) {
            var field_spec = this.fields[field];
            if (field_spec.timeout_css != undefined) {
                this.timeout_styler = new TimeoutStyler(this.container_div,
                                                        field_spec.timeout_css);
            }
        }

    }.bind(this);
    document.addEventListener('DOMContentLoaded', this.chart);

    // When passed a websocket server /data report, sifts through
    // fields and updates any series with matching field names.
    this.process_message = function(message) {
        if (this.timeout_styler != null) {
            this.timeout_styler.reset_timers()
        }
        var container_div = document.getElementById(this.container);
        if (!container_div) {
            console.log('Unable to find container id "' + this.container
                        + '" in page?')
            return;
        }
        for (var field_name in this.fields) {
            if (!message[field_name]) {
                continue;
            }
            var value_list = message[field_name],
                value_str = '';

            // If they've instructed us to append new values (and
            // if new value is non-empty), append it. If they've
            // specified a separator, use it; otherwise use
            // semicolon.
            if (this.fields[field_name].append) {
                // Values are [timestamp, value] pairs. Add sequentially.
                for (var list_i = 0; list_i < value_list.length; list_i++) {
                    var value = value_list[list_i][1];
                    if (this.fields[field_name].transform) {
                        value = this.fields[field_name].transform(value);
                    }
                    if (value.length > 0) {
                        var sep = this.fields[field_name].separator || '; ';
                        value_str += sep + value;
                    }
                }
            }
            // If not appending, just set to last value in list
            else {
                value_str = value_list[value_list.length-1][1];
                if (this.fields[field_name].transform) {
                    value_str = this.fields[field_name].transform(value_str);
                }
            }
            // Finally, assign to container html
            container_div.innerHTML = value_str;
        }
    }
}
