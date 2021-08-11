//////////////////////////////////////////////////////////////////////////////
// Javascript for fetching log lines whose data_id matches some data_id,
// such as 'stderr:logger:s330', and appending them to a specified target div.
//
// Typical invocation will look like:
//
//    <script type="text/javascript">
//      var WEBSOCKET_SERVER = 'localhost:8766';
//      var CDS_DATA_ID = 'stderr:logger:' + LOGGER_ID;
//      var CDS_TARGET_DIV = LOGGER_ID + '_stderr';
//    </script>
//    <script src="/static/django_gui/fetch_cds_logs.js"></script>
//    <script src="/static/django_gui/websocket.js"></script>
//

////////////////////////////
function initial_send_message() {
  // Have to put this together piece by piecce because JS is stupid.
  var seconds_of_back_logs = 60*60;
  var fields = {};
  fields[CDS_DATA_ID] = {'seconds': seconds_of_back_logs};
  var initial_message = {'type': 'subscribe',
                         'fields': fields};
  return initial_message;
}

////////////////////////////
function process_message(message_str) {
  // Just for debugging purposes
  var message = JSON.parse(message_str);

  // Figure out what kind of message we got
  var message_type = message.type;
  var status = message.status;

  // If something went wrong, complain, and let server know we're ready
  // for next message.
  if (status != 200) {
    console.log('Error from server: ' + message_str);
    return;
  }
  // Now go through all the types of messages we know about and
  // deal with them.
  switch (message_type) {
    case 'data':
      //console.log('Got data message. Processing...');
      process_data_message(message.data);
      break;
    case 'subscribe':
      if (status != 200) {
        console.log('Subscribe request failed: ' + message_str);
      }
      break
    case undefined:
      console.log('Error: message has no type field: ' + message_str);
      break;
    default:
      console.log('Error: unknown message type "' + message_type + '"');
  }
}

////////////////////////////
// Process CDS data message (hopefully) containing log lines and add
// to the div we've been passed.
function process_data_message(message) {
  // We expect to receive a field dict, format:
  // {
  //   'data_id': ...,  # optional
  //   'fields': {
  //      field_name: [(timestamp, value), (timestamp, value),...],
  //      field_name: [(timestamp, value), (timestamp, value),...],
  //      ...
  //   }
  // }
  if (!message || message.length == 0) {
    return;
  }

  var new_messages = '';
  for (var field_name in message) {
    if (field_name.indexOf(CDS_DATA_ID) != 0) {
      console.log('Ignoring unexpected field name: ' + field_name);
      continue;
    }
    var value_list = message[field_name];
    // Process each of the messages in value_list.
    for (var list_i = 0; list_i < value_list.length; list_i++) {
      // Skip duplicate messages
      if (list_i > 0 && value_list[list_i] == value_list[list_i-1]) {
        continue;
      }
      var [timestamp, message] = value_list[list_i];

      // Clean up message and add to new_messages list
      message = message.replace('\n','<br>') + '<br>\n';
      new_messages += color_message(message);
    }
  }
  // Once all messages have been added, fetch the div where we're
  // going to put these messages, and add them.
  if (new_messages.length) {
    var stderr_div = document.getElementById(CDS_TARGET_DIV);
    if (stderr_div) {
      stderr_div.innerHTML += new_messages;
      stderr_div.scrollTop = stderr_div.scrollHeight;  // scroll to bottom
    } else {
      console.log('Couldn\'t find div for ' + CDS_TARGET_DIV);
    }
  }
}

// Add HTML coloring to message depending on log level
function color_message(message) {
  var color = '';
  if (message.indexOf(' 30 WARNING ') > 0) {
    color = 'gold';
  } else if (message.indexOf(' 40 ERROR ') > 0) {
    color = 'orange';
  } else if (message.indexOf(' 50 CRITICAL ') > 0) {
    color = 'red';
  }
  if (color !== '') {
    message = '<span style="color:' + color + '">' + message + '</span>';
  }
  return message;
}
