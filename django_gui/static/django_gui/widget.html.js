//////////////////////////////////////////////////////////////////////////////
// Javascript behind and specific to the index.html page.
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
//    <script src="/static/django_gui/widget.html.js"></script>
//    <script src="/static/django_gui/websocket.js"></script>
//
// Note that this also counts on variables WEBSOCKET_SERVER and
// FIELD_LIST being set in the calling page.

////////////////////////////////////////////////////////////////////
// Widget-specific functions

///////////////////////////
function initial_send_message() {
  var fields = {};
  var field_list = FIELD_LIST;
  for (f_i = 0; f_i < field_list.length; f_i++) {
    var field = field_list[f_i];
    fields[field] = {'seconds':-1};
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
    for (var field_name in data_dict) {
      var value_list = data_dict[field_name];
      var last_pair = value_list[value_list.length-1];
      var timestamp = last_pair[0];
      var value = last_pair[1];
      var td = document.getElementById(field_name + '_value');
      td.innerHTML = value

      var ts_td = document.getElementById('timestamp');
      ts_td.innerHTML = Date(timestamp * 1000);
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
