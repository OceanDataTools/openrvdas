/*******************************************************************************
Create a text widget. See README.md for full documentation.

********************************************************************************/

function TextWidget(container, fields) {
  this.fields = fields;
  this.container = container;

  this.chart = function() {
    var internals = '';
    // Create one span for each field
    for (var id in fields) {
      internals += '<span id=' + container + '-' + id + '></span>';
    }

    var container_div = document.getElementById(container);
    if (container_div) {
      container_div.innerHTML = internals;
    } else {
      console.log('TextWidget unable to find container div \"'
                   + container +'\"');
    }
  }

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
      // Find the div we're going to update
      var field_div = document.getElementById(container + '-' + field_name);
      if (!field_div) {
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
        field_div.innerHTML = value;
      }
    }
  }
}
