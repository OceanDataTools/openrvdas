//////////////////////////////////////////////////////////////////////////////
// Connect to a websocket server to request data from it.
//
// Typical invocation will look like:
//
//    <script type="text/javascript">
//      // Need to define for following JS scripts. For now, count on the
//      // relevant variables being set by Django.
//      var WEBSOCKET_SERVER = "{{ websocket_server }}";
//    </script>
//
//    <script src="/static/django_gui/index.html.js"></script>
//    <script src="/static/django_gui/websocket.js"></script>
//
// Relies on initial_send_message() and process_message() being defined
// by a previous script (in this// case index.html.js), where
// initial_send_message() should return a CachedDataServer command that
// will initiate receipt of the desired data, and process_message(mesg)
// will be called on the data received from that initial message and
// future messages.
//
// Note that this also counts on variable WEBSOCKET_SERVER  being set
// in the calling page.

////////////////////////////////////////////////////////////////////////////////
var websocket_server = WEBSOCKET_SERVER;
// It's possible that we get an empty hostname, e.g. 'wss://:8000/cds-ws
if (websocket_server.indexOf('//:') > 0) {
  websocket_server = websocket_server.replace('//:', '//' + location.hostname + ':');
}

//////////////////////////////////////////////////////////////
if (! "WebSocket" in window) {
  alert("Warning: websockets not supported by your Browser!");
}

// Set timer to retry websocket connection if it closes. Interval is
// turned off in ws.onopen() if/when we succeed.
var retry_interval = 3000;
var retry_websocket_connection;
var ws;

// Try connecting right off the bat
connect_websocket();

//////////////////////////////////////////////////////
function connect_websocket() {
  console.log("Trying to connect to websocket at " + websocket_server);
  ws = new WebSocket(websocket_server);
  
  ws.onopen = function() {
    // We've succeeded in opening - don't try anymore
    console.log("Connected - clearing retry interval");
    clearTimeout(retry_websocket_connection);

    // Send our first message to get things going.
    var initial_message = initial_send_message();
    send(initial_message);
  }
  ws.onclose = function() { 
    // websocket is closed.
    console.log("Connection is closed...");

    // Set up an alarm to sleep, then try re-opening websocket
    console.log("Setting timer to reconnect");
    retry_websocket_connection = setTimeout(connect_websocket,
                                            retry_interval);
  };

  ws.onmessage = function (received_message) { 
    //console.log("Got status update message: " + received_message.data);
    process_message(received_message.data);
    //console.log('done processing message');
    send({'type':'ready'})
  };
};

window.onbeforeunload = function(event) {
  console.log("Closing websocket");
  ws.close();
};

function send(message) {
  //console.log("Sending message '" + JSON.stringify(message) + "'");
  ws.send(JSON.stringify(message));
};
