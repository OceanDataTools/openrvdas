/*******************************************************************************
Create a text widget. See README.md for full documentation.

NOTE: Much of this code is an artifact from an earlier iteration when
each widget could have multiple fields. Now we require/expect/hope
that each widget has just a single data field. If it has multiple
fields, we'll complain, but then update the innerHTML of our container
from every one of the fields in sequence.

********************************************************************************/

function TextWidget(container, fields) {
    this.fields = fields;
    this.container = container;

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
    }
    document.addEventListener('DOMContentLoaded', this.chart);

    // When passed a websocket server /data report, sifts through
    // fields and updates any series with matching field names.
    this.process_message = function(message) {
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
