//////////////////////////////////////////////////////////////////////////////
//
// sqlite_gui/websocket.js
//
// The class for the websocket connection to the cached data server
//
// The only method of interest to most people will be 
// WS.write(argument)
//     The argument will be converted to JSON and sent to the websocket.
//
// The websocket name can either be specified in the config file
// (openrvdas.json), or if not specified (or specified as ""),
// this routine will take a "best guess".
//
// This is usually placed last in the list of included scripts.
// If you want to try a different ordering, go for it, let me
// know how it works out.
//

/////////////////////////////////////////////////////////////////////
//
// Websocket code
//
/////////////////////////////////////////////////////////////////////

var WS = (function() {
    // Start by chastising people with sucky browsers
    if (!("WebSocket" in window)) {
        alert("Warning: websockets not supported by your browser!");
        return false;
    }

    // If we don't have a websocket server defined, guess
    var retry_interval = 3000;
    var parser_queue = [];
    // rwc = retry_websocket_connection
    var rwc;
    var ws;
    var sock;
 
    var initial_send_message = { 
        'type':'subscribe',
        'fields': {
	    'status:cruise_definition':{'seconds':-1},
	    'status:cruise_mode':{'seconds':-1},
	    'status:logger_status':{'seconds':-1},
	    'status:file_update':{'seconds':0},
	    // Get logger manager stderr, too.
	    'stderr:logger_manager':{'seconds': 60*60}
        }
    };


    function connect_websocket() {
        try {
            // config object (odas) may not exist.  Fallback.
            var o = odas || {};
            url = odas.ws || "";
            if (url == "") {
                var proto = 'ws://';
                var p = document.location.protocol;
                if (p == 'https:') {
                    proto = 'wss://';
                }
                port = "";
                p = document.location.port;
                if (p != "") {
                    port = ":" + p;
                }
                url = proto + document.location.host + port + '/cds-ws';
            } 
            sock = new WebSocket(url);
        } catch (err) {}

        sock.onopen = function() {
            clearTimeout(rwc);
            write(initial_send_message);
        };

        sock.onclose = function() { 
            // Set up an alarm to sleep, then try re-opening websocket
            console.warn("Websocket closed, trying to reconnect");
            rwc = setTimeout(connect_websocket, retry_interval);
        };

        // Some socket errors won't quickly close the connection,
        // To speed things up, close it ourselves.  If the error
        // already closed the connection, this does no harm.
        sock.onerror = function(event) {
            console.error("Websocket error received", event);
            sock.close(1000, "Due to client receiving an error");
        };

        sock.onmessage = function (received_message) { 
            var data = received_message.data;
            parser_queue.forEach(function(func){ func(data); } );
            write({'type':'ready'});
        };

        // If we're deliberately closing, don't set a timer to
        // autoreconnect.  That would just be silly.
        window.onbeforeunload = function(event) {
            console.debug("Closing websocket");
            sock.onclose = {};
            sock.close();
        };
    }
    connect_websocket();

    // Used to add additional methods to message parser.
    // Not sure why we'd want more than one, but I remember
    // needing something like this in another project, so....
    var add_parser = function(parser) {
        if (parser_queue.includes(parser)) { return; }
        parser_queue.push(parser);
    };

    // This is our default function name for the message parser.
    // If it's defined, add it automatically.
    if (typeof process_message === 'function') {
        add_parser(process_message);
    }

    // While there's basically nothing wrong with the way 'send' was
    // defined previously, it's pretty much better to make it a 
    // method of our websocket object.  Makes it clear that we're
    // performing a websocket operation.  A bare "send" is ambiguous
    // when seen elsewhere to someone not familiar with the code.
    var write = function(msg) {
        sock.send(JSON.stringify(msg));
    };

    return {
        ws: sock,
        add_parser: add_parser,
        write: write
    };
})();

