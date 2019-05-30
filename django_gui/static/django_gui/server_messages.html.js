//////////////////////////////////////////////////////////////////////////////
// Javascript behind and specific to the server_messages.html page.
//
// Typical invocation will look like:
//
//    <script type="text/javascript">
//      // Need to define for following JS scripts. For now, count on the
//      // relevant variables being set by Django.
//      var WEBSOCKET_SERVER = "{{ websocket_server }}";
//      var FIELD_LIST_STRING = '{{ field_list }}';
//    </script>
//
//    <script src="/static/django_gui/server_messages.html.js"></script>
//    <script src="/static/django_gui/websocket.js"></script>
//
// Note that this counts on variables WEBSOCKET_SERVER and
// FIELD_LIST being set in the calling page.

////////////////////////////////////////////////////////////////////
// Widget-specific functions

//function resize_table() {
//  var window_height = window.innerHeight;
//  console.log('RESIZED to ' + window_height);
//  var server_message_div = document.getElementById('server_message_div');
//  console.log('Table height now ' + server_message_div.style.height);
//  server_message_div.style.height = (window_height - 100) + 'px';
//}
//window.addEventListener('resize', resize_table);

///////////////////////////
function initial_send_message() {
  var fields = {};
  var field_list = FIELD_LIST;
  for (f_i = 0; f_i < field_list.length; f_i++) {
    var field = field_list[f_i];
    fields[field] = {'seconds':100000};
  }
  return {'type':'subscribe', 'fields': fields};
}

///////////////////////////////////////////////////////////////
function process_message(message_str) {
  var message = JSON.parse(message_str);

  // Figure out what kind of message we got
  var message_type = message.type;
  var status = message.status;

  switch (message_type) {
  case 'data':
    var data_dict = message.data;
    if (data_dict == undefined) {
      console.log('Got data message with no data?!?: ' + message_str);
      return;
    }
    // Fill in the values we've received
    var server_messages = document.getElementById("server_messages");

    // Is display at bottom of table? If so, we'll scroll down after
    // adding new entries.
    var page_bottom = server_messages.scrollHeight;
    var page_position = server_messages.scrollTop+server_messages.clientHeight;
    var at_bottom = (page_bottom == page_position);

    for (var field_name in data_dict) {
      var value_list = data_dict[field_name];
      console.log('Got ' + data_dict[field_name].length + ' values for '
                  + field_name);
      for (var vl_i = 0; vl_i < value_list.length; vl_i++) {
        var element = value_list[vl_i];
        var value = element[1];
        var [log_level, level_name, timestamped_message] = value.split('\t', 3);
        var parts = timestamped_message.split(' ');
        var timestamp = parts[0];
        var message = parts.slice(1).join(' ');

        // If log level is greater than the level of this message, skip it
        if (LOG_LEVEL > log_level) {
          continue;
        }

        var tr = document.createElement("tr");
        var td = document.createElement("td");
        td.appendChild(document.createTextNode(timestamp));
        tr.appendChild(td);
        var td = document.createElement("td");
        td.appendChild(document.createTextNode(level_name));
        tr.appendChild(td);
        var td = document.createElement("td");
        td.appendChild(document.createTextNode(message));
        tr.appendChild(td);

        // Set message color if it's a warning or error
        for (var level in LOG_LEVEL_COLORS) {
          var level_color = LOG_LEVEL_COLORS[level];
          if (log_level == level) {
            tr.style.backgroundColor = level_color;
          }
        }
        server_messages.appendChild(tr);
      }
    }
    // If window was at bottom before we added new stuff, scroll down
    // to keep it at the bottom.
    if (at_bottom) {
      server_messages.scrollTop = server_messages.scrollHeight 
        + server_messages.clientHeight;
    }
    break;
  case 'subscribe':
    if (status != 200) {
      console.log('Got bad status for subscribe request: ' + message_str);
      console.log('Original subscribe request: '
                  + JSON.stringify(initial_send_message()));
    }
    break;
  case 'ready': // if no data are ready
    console.log('no data ready');
    break;
  default: 
    console.log('Got unknown message type: ' + message_str);
  }
}

// Sleep function we'll use if there are no data ready
const sleep = (milliseconds) => {
  return new Promise(resolve => setTimeout(resolve, milliseconds))
}
