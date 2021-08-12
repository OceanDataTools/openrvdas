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
//    <script src="/static/django_gui/stderr_log_utils.js"></script>
//    <script src="/static/django_gui/edit_configs.js"></script>
//    <script src="/static/django_gui/websocket.js"></script>
//
//  NOTE: ORDERING IS IMPORTANT.

  ////////////////////////////
  // Called by websocket.js to construct initial message to send to
  // cached data server when websocket is opened: subscribe to
  // messages matching CDS_DATA_ID
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
  // Invoked by websocket.js when messages are received. Parse message and
  // add to CDS_TARGET_DIV
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
        // If it's a data message, assume it's a stderr_log message. Call
        // the handler defined in stderr_log_utils.js
        var logger_id = CDS_DATA_ID;
        var target_div_id = CDS_TARGET_DIV;
        var log_line_list = message.data[logger_id];
        if (log_line_list) {
          // defined in stderr_log_utils.js
          process_stderr_message(logger_id, target_div_id, log_line_list);
        } else {
            //console.log('edit_config message for ' + logger_id + ' didn\'t ' +
            //            'contain expected stderr log key');
            //console.log(JSON.stringify(message.data));
        }
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
