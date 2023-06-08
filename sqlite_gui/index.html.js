///////////////////////////////////////////////////////////////////////////////
// Javascript for 'index.html'
//
// Typical invocation will look like:
//
//    <script type="text/javascript">
//      // Need to define for following JS scripts. For now, count on the
//      // relevant variables being set by Django.
//      var WEBSOCKET_SERVER = "{{ websocket_server }}";
//      {% if user.is_authenticated %}
//        var USER_AUTHENTICATED = true;
//      {% else %}
//        var USER_AUTHENTICATED = false;
//      {% endif %}
//    </script>
//
//    <script src="/static/django_gui/index.html.js"></script>
//    <script src="/static/django_gui/websocket.js"></script>
//
// Note that this also counts on variables USER_AUTHENTICATED and
// WEBSOCKET_SERVER being set in the calling page.

// User servicable parts
// FIXME: Should probably be part of the config, otherwise roll
//        them into their objects/classes
//var NOW_TIMEOUT_INTERVAL = 1000;     // Update console clock every second
//var SERVER_TIMEOUT_INTERVAL = 5000;  // 5 seconds before warn about server
//var STATUS_TIMEOUT_INTERVAL = 10000; // 10 seconds before warn about status
////////////////////////////////////////////////////////////////////
//
//  The 'now' element was previously only updated when a message
//  was received from the server.  This is probably not the 
//  intended behaviour.  I think we want to update the 'now'
//  element more or less in real time, regardless of whether we
//  have contact with the server or not.
// 
////////////////////////////////////////////////////////////////////
    
var time_td = (function() {
    var el = document.getElementById('time_td');
    if (!el) { return; }
    // default timeout if no value in config file
    // FIXME:  This actually evaluates before the JSON is loaded,
    //         so the config file basically does nothing.
    var t = 1000;

    function update_now() {
        if (!el) { return; }
        el.innerHTML = Date().substring(0, 24);
    }
    var interval = setInterval(update_now, t);
 
    // We could probably wait one second to write the time, but...
    update_now();

    return {
        el: el,
    }
        
})();

////////////////////////////////////////////////////////////////////
//
//  Handle the updates of the status_time_td
//
////////////////////////////////////////////////////////////////////
var status_td = (function() {
    // FIXME:  Tooltip "last status from logger_manager"
    var el = document.getElementById('status_time_td');
    if (el) {
        el.className = '';
    }

    // Default timeout 10 seconds, over-ride by config
    var t = 10000;
    if (odas) {
        if (odas.Timeouts) {
            t = odas.Timeouts.Status * 1000;
        }
    }

    var timer = setTimeout(timed_out, t);

    function timed_out() {
        if (el) {
            el.className = 'text-danger';
        }
    }

    var update = function() {
        clearTimeout(timer);
        timer = setTimeout(timed_out, t);
        if (el) {
            el.innerHTML = Date().substring(0,24);
            el.className = '';
        }
    }

    return {
        update: update
    }
})();

////////////////////////////////////////////////////////////////////
//
//  Handle the updates of the server_time_td
//
////////////////////////////////////////////////////////////////////
var server_td = (function() {
    // FIXME:  Tooltip "last update from CDS"
    var el = document.getElementById('server_time_td');
    el.className = '';

    // Default timeout 5 seconds, over-ride by config
    var t = 5000;
    if (odas) {
        if (odas.Timeouts) {
            t = odas.Timeouts.Server * 1000;
        }
    }

    var timer = setTimeout(timed_out, t);

    function timed_out() {
        if (el) {
            el.className = 'text-danger';
        }
    }

    var update = function() {
        clearTimeout(timer);
        timer = setTimeout(timed_out, t);
        if (el) {
            el.innerHTML = Date().substring(0,24);
            el.className = '';
        }
    }

    return {
        update: update
    }
})();


////////////////////////////////////////////////////////////////////
//
//  Called by the websocket's onmessage callback.
//  Updates server_time
//  Processes messages based on data type
//
////////////////////////////////////////////////////////////////////
function process_message(message_str) {
    // Update time of last message from websocket
    server_td.update(); 

    var message = JSON.parse(message_str);
    // If something went wrong, complain, and let server know we're ready
    // for next message.
    if (message.status != 200) {
        // Maybe set a badge somewhere?
        console.warn('Error from server: ' + message_str);
        return;
    }

    // Now go through all the types of messages we know about and
    // deal with them.
    switch (message.type) {
        //console.log("message.type = ", message.type);
        case 'data':
            process_data_message(message.data);
            break;
        case 'subscribe':
            //console.log('Subscribe request successful');
            break;
        case undefined:
            Q = "Error: meesage has no type field: "
            console.warn(Q, message_str);
            break;
        default:
            Q = "Error: unknown message type (";
            console.warn(Q, message.type, ')');
    }
}

var CruiseDef = (function() {
    var our_timestamp = 0;
    var el_empty =  document.getElementById('empty_loggers');
    var el_populated = document.getElementById('status_and_loggers');
    var loggers = {}

    function diff_loggers(config_loggers) {
        var new_loggers = [];   // new loggers we don't have
        var old_loggers = [];    // loggers we had that are gone

        // Hmmm. performance wise, it is faster to do it this way?
        var new_set = new Set(Object.keys(config_loggers));
        var old_set = new Set(Object.keys(loggers));

        for (var logger of new_set) {
            if (old_set.has(logger)) {
                continue;
            }
            new_loggers.push(logger);
        }
        for (logger of old_set) {
            if (new_set.has(logger)) {
                continue;
            }
            old_loggers.push(logger);
        }
        return {
            new: new_loggers,
            old: old_loggers,
            size: new_loggers.length + old_loggers.length,
        }
    }

    function show_correct_divs(config) {
        // Interwebs says using the classes works better
        // than setting visibility on mobile.  May be true.
        // Why are we actually doing this?
        if (config.loggers) {
            el_empty.className = "d-none";
            el_populated.className = "d-block";
        } else {
            el_empty.className = "d-block";
            el_populated.className = "d-none";
        }
    }

    function update_cruise_id(cruise_id, filename) {
        var el = document.getElementById('cruise_id');
        if (el) {
            txtNode = el.childNodes[0];
            txtNode.nodeValue = cruise_id;
            // Add tooltip with definition file name
            // cruise_definition.filename
        }
        // FIXME;  For now, we're doing this.  Yuk!
        el = document.getElementById('LoadConfig_link');
        if (el) {
            el.setAttribute('data-bs-toggle', 'tooltip');
            el.setAttribute('title', filename);
        }
    }

    function update_logger_rows(loggers) {

    }

    // Called when a message of type "status:cruise_definition"
    // arrives on the websocket
    var status_message = function(timestamp, config) {
        if (timestamp < our_timestamp) {
            console.debug('Stale status:cruise_definition message');
            return;
        }
        our_timestamp = timestamp;
        show_correct_divs(config);
        // var new_fields = update_cruise_definition(timestamp, config);
        // Ensure all the correct parts are there
        if (!config.modes) {
            console.log('Cruise definition has no modes - ignoring.');
            return {};
        }
        if (!config.active_mode) {
            console.log('Cruise definition has no active mode - ignoring.');
            return {};
        }
        if (!config.loggers) {
            console.log('Cruise definition has no loggers - ignoring.');
            return {};
        }
        // update cruise name on navbar
        if (config.cruise_id) {
            update_cruise_id(config.cruise_id, config.filename);
        }
        // Set the cruise mode button to the active mode
        active_mode = config.active_mode;
        cruise_mode.update(active_mode);
        // get diff between old loggers and config.loggers
        // We could just add the new ones and delete the old ones,
        // but that would change the order.  I think we care...
        var diff = diff_loggers(config.loggers);
        loggers = config.loggers;
        console.info('Loaded new configuration');
        console.info("odas = ", JSON5.stringify(odas, null, "  "));
        if (odas) {
            odas.api = config;
        }
        if (diff.size == 0) {
           // Set the logger button texts
           // FIXME:  I think we already have a function for this.
           for (var logger_name in loggers) {
                var button = document.getElementById(logger_name + '_btn');
                if (button) {
                    button.innerHTML = loggers[logger_name].active;
                }
            }
            return {};
        } else {
            update_logger_rows(loggers);
        }
        var foo = 'bar';
        // If stuff has gotten updated, need to update CDS fields to
        // subscribe to.
        var new_fields = {};

        // Update logger_manager status, resubscribe to updates asking for greater
        // of last hour of records or last 100 records.
        // var button = document.getElementById('logger_manager_mode_button');
        //button.innerHTML = global_active_mode;
        var time_window = {'seconds':1*60*60, 'back_records': 100};
        new_fields['stderr:logger_manager'] = time_window;

        ////////////////////////////////
        // If the list of loggers has changed, we need to rebuild the
        // list. Begin by emptying out table rows except for header row.
        var table = document.getElementById('logger_table_body');
        try {
            var row_count = table.rows.length;
            var keep_first_num_rows = 3;
            for (var i = keep_first_num_rows; i < row_count; i++) {
                table.deleteRow(keep_first_num_rows);
            }
        } catch {}

        // Stash our new logger list in the globals, then update the
        // loggers, creating one new row for each.
        for (var logger_name in loggers) {
            //console.log('setting up logger ' + logger_name);
            var logger = loggers[logger_name];

            // table row creation
            var tr = document.createElement('tr');
            tr.setAttribute('id', logger_name + '_row');

            var config_td = document.createElement('td');
            config_td.setAttribute('id', logger_name + '_config_td');

            var button = LoggerButton.create(logger_name, logger.active);
            config_td.appendChild(button);
            tr.appendChild(config_td);

            var stderr_td = document.createElement('td');
            var stderr_div = document.createElement('div');

            stderr_div.setAttribute('id', logger_name + '_stderr');
            stderr_div.className = 'stderr_window';
            stderr_td.appendChild(stderr_div);
            tr.appendChild(stderr_td);
            table.appendChild(tr);

            // Also, since we now have a new logger, we'll want to
            // subscribe to stderr updates for it.  Send each logger
            // window with at greatest of one hour past log messges or
            // most recent 100 messages
            var name = 'stderr:logger:' + logger_name
            new_fields[name] = time_window;
            new_fields['stderr:logger:' + logger_name] = {'seconds':6*60*60, 'back_records': 100};
        }
        //console.log('New fields are: ' + JSON.stringify(new_fields));
        //////////////////
        // Finally: Do we have new field subscriptions? Create the
        // subscription request.  But make sure we keep listening for future
        // logger_list, mode_list mode updates.
        // FIXME:  Are new_fields used anywhere besides cruise_definition?
        if (Object.keys(new_fields).length) {
            new_fields['status:cruise_definition'] = {'seconds':-1};
            new_fields['status:cruise_mode'] = {'seconds':-1};
            new_fields['status:logger_status'] = {'seconds':-1};
            new_fields['status:file_update'] = {'seconds':0};
            var subscribe_message = {'type':'subscribe', 'fields':new_fields};
            WS.write(subscribe_message);
        }
    }
        
    return {
        status_message: status_message,
    }   

})()

////////////////////////////
////////////////////////////
// We've got data fields - process and put them where they belong in
// the HTML...
function process_data_message(message) {
    //console.log('Got new data message: ' + JSON.stringify(message));
    //
    // We expect to receive a field dict, format:
    // {
    //   'data_id': ...,  # optional
    //   'fields': {
    //      field_name: [(timestamp, value), (timestamp, value),...],
    //      field_name: [(timestamp, value), (timestamp, value),...],
    //      ...
    //   }
    // }
  
    //console.log("process_data_message: ", JSON.stringify(message));
    var new_fields = {};

    for (var field_name in message) {
        // If we receive a status update, update the status time
        if (field_name.startsWith('status:')) {
            status_td.update();
        }
        var value_list = message[field_name];
        // Get the [timestamp, value] pair at the end of the list.
        // That should be the most recent.
        var [ timestamp, values ] = value_list[value_list.length - 1];
        // Do we want to make a dispatch table for these?
        // if (key) { func['field_name'] }
        switch (field_name) {
            // Cruise definition updatee
            case 'status:cruise_definition':
                var nf = CruiseDef.status_message(timestamp, values);
                // var nf = status_cruise_definition(timestamp, values);
                // for (var key in nf) {
                //    new_fields[key] = nf[key];
                // }
                break;

            // Cruise Mode update
            case 'status:cruise_mode':
                if (typeof(global_last_cruise_timestamp) == 'undefined') {
                    global_last_cruise_timestamp = 0;
                }
                if (timestamp < global_last_cruise_timestamp) {
                    break;
                }
                global_last_cruise_timestamp = timestamp;
                update_cruise_mode(timestamp, values);
                break;

            // Logger Status update
            case 'status:logger_status':
                //update_logger_status(timestamp, values);
                LoggerButton.update(timestamp, values);
                break;

            //////////////////
            // The file from which our definition came has been updated. Make
            // the section that offers to reload it visible. If user is not
            // authenticated, this element will not exist.
            // File_update update
            case 'status:file_update':
                // FIXME:  This needs to go on the menubar.
                //         Using a badge might be a good idea.
                //         Dynamically add something to the dropdown?
               var reload_span = document.getElementById('reload_span');
               if (reload_span) { reload_span.style.display = 'inline' }
               break;

            case 'stderr:logger_manager':
                STDERR.process('logger_manager_stderr', value_list);
                break;

            ////////////////////////////////////////////////////
            // If something else, see if it's a logger status update
            default:
                var LOGGER_STDERR_PREFIX = 'stderr:logger:';
                if (field_name.indexOf(LOGGER_STDERR_PREFIX) == 0) {
                    var logger_name = field_name.substr(LOGGER_STDERR_PREFIX.length);
                    // Defined in stderr_log_utils.js
                    var target = logger_name + '_stderr'
                    STDERR.process(target, value_list);
                }
        }

    }
}


var cruise_mode = (function() {
    var mode_button = document.getElementById('mode_button');
    var timestamp = 0;

    function init() {
        // attach events to the button
    }

    // Called when we get a message saying the mode has changed
    function update(new_mode) {
        global_active_mode = new_mode;
        if (mode_button) {
            mode_button.innerHTML = new_mode;
        }
    }

    // Called when we receive a status update from the CDS
    function status_update(timestamp, value) {
    
    }

    init();

    return {
        update: update,
        status_update: status_update,
    }
})();

////////////////////////////
// Process a cruise_mode update
function update_cruise_mode(timestamp, cruise_mode) {
//                if (timestamp < global_last_cruise_timestamp) {
//                    break;
//                }
//                global_last_cruise_timestamp = timestamp;
//                update_cruise_mode(timestamp, values);
    var new_mode = cruise_mode.active_mode;
    global_active_mode = new_mode;
    var mode_button = document.getElementById('mode_button');
    mode_button.innerHTML = new_mode;
}

////////////////////////////////////////////////////
// If we've got a logger status update. Status will be a dict of
// logger_name:status pairs. 'status' will be an array of:
//
//   logger_name: {
//     config:  config_name_string,
//     errors:  [list of error strings],
//     failed:  bool
//     pid:     number or null if not running
//     running: ternary value:
//       true:  we're running and is supposed to be
//       false: not running and is supposed to be
//       null:  not running and not supposed to be
//   }

