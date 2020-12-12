//////////////////////////////////////////////////////////////////////////////
// Create a widget server that will try to connect to a data server on
// the specified websocket and request/serve data for all the widgets
// it has been created with. Sample invocation:
//
//    var widget_list = [];
//    widget_list.push(new TextWidget('pitch_container',
//                     pitch_fields, 'Degrees'));
//    widget_list.push(new TextWidget('roll_container', roll_fields, 'Degrees'));
//
//    var widget_server = new WidgetServer(widget_list, 'localhost:8765');
//    widget_server.serve();
//
// See README.md for full documentation

////////////////////////////////////////////////////////////////////////////////
if (! 'WebSocket' in window) {
  alert('Warning: websockets not supported by your Browser!');
}

////////////////////////////////////////////////////////////////////////////////
function WidgetServer(widget_list, websocket_server) {
  this.websocket_server = websocket_server;
  // Syntactic sugar - can pass in either a widget or a list of widgets.
  // If they've given us a single widget, wrap it into a list.
  if (!Array.isArray(widget_list)) {
    widget_list = [widget_list];
  }
  this.widget_list = widget_list;

  this.websocket_server = websocket_server;
  this.data_request = build_data_request(widget_list);

  // placeholder for retry timer
  this.retry_websocket_connection;
  this.RETRY_INTERVAL = 3000;

  ///////////////////////////////
  // Attempt to open the websocket connection; if we succeed, send
  // the data request we've prepared.
  this.serve = function() {
    console.log('Trying to reconnect to websocket server at ' + this.websocket_server);
    this.ws = new WebSocket(this.websocket_server);

    ////////////////
    this.ws.onopen = function() {
      // We've succeeded in opening - don't try anymore
      console.log('Connected - clearing retry interval');
      clearTimeout(this.retry_websocket_connection);

      // Web Socket is connected, send data using send()
      this.ws.send(this.data_request);
      console.log('Sent initial message: ' + this.data_request);
    }.bind(this);

    ////////////////
    this.ws.onclose = function() {
      // Websocket is closed.
      console.log('Connection is closed...');

      // Set up an alarm to sleep, then try re-opening
      // websocket. Interval is turned off in ws.onopen()
      // if/when we succeed.
      console.log('Setting timer to reconnect');
      this.retry_websocket_connection =
        setTimeout(this.serve, this.RETRY_INTERVAL);
    }.bind(this);

    ////////////////
    this.ws.onmessage = function (received_message) {
      var parsed_message = JSON.parse(received_message.data);

      switch (parsed_message.type) {
      case 'data':
        // Pass parsed message data to each widget's process_message() func
        var data = parsed_message.data;
        if (data == undefined) {
          console.log('No data in message of type data: ' + received_message);
        } else {
          for (widget_i = 0; widget_i < this.widget_list.length; widget_i++) {
            var widget = this.widget_list[widget_i];
            widget.process_message(data);
          }
        }
        break;
      case 'ready':
      case 'subscribe':
        break
      default:
        console.log('Got unexpected message type: ' + received_message);
      }
      // Let server know we're ready for our next message
      this.ws.send('{"type":"ready"}');
    }.bind(this);

    window.onbeforeunload = function(event) {
      console.log("Closing websocket");
      this.ws.close();
    }.bind(this);
  }.bind(this)
};

////////////////////////////////////////////////////////////////////////////////
// Build data request to send to server. Format is an associative array:
//
//   { field_name: {seconds: num_sec},
//     field_name: {seconds: num_sec},
//     ...
//   }
//
// where num_sec is the number of seconds of back data we want for
// that data field. If a field is required by multiple sources,
// use the max of number of seconds requested.
function build_data_request(widget_list) {
  var field_array = {};
  for (var widget_i = 0; widget_i < widget_list.length; widget_i++) {
    var widget = widget_list[widget_i];
    for (field_name in widget.fields) {
      var field_seconds = widget.fields[field_name].seconds || -1;
      if (field_array[field_name] === undefined) {
        field_array[field_name] = {};
      }
      if (field_array[field_name].seconds === undefined ||
          field_seconds > field_array[field_name].seconds) {
        field_array[field_name].seconds = field_seconds;
      }
      if (widget.fields[field_name].subsample) {
        field_array[field_name].subsample = widget.fields[field_name].subsample;
      }
    }
  }
  var request = {'type':'subscribe', 'fields':field_array}
  return JSON.stringify(request, undefined, 2);
  //return JSON.stringify(request);
}
