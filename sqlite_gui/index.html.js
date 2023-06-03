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
(function() {
    var el = document.getElementById('time_td');
    if (!el) { return; }
    // default timeout 
    var t = 1000;
    if (odas) {
        if (odas.Timeouts) {
            t = odas.Timeouts.Now * 1000;
        }
    }

    function update_now() {
        el.innerHTML = Date().substring(0, 24);
    }
    // Even if we don't have a time_td on whatever page this
    // gets loaded on, this does little harm.
    var interval = setInterval(update_now, t);
 
    // We could probably wait one second to write the time, but...
    update_now();
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

function status_cruise_definition(timestamp, config) {
    if (timestamp < global_last_cruise_timestamp) {
        // stale update.  ignore.
        return;
    }
    // console.debug("cruise_def_updated()");
    global_last_cruise_timestamp = timestamp;
    var new_fields = update_cruise_definition(timestamp, config);
    var el =  document.getElementById('empty_loggers');
    var sal = document.getElementById('status_and_loggers');
    // Show/hide empty_logger, status_and_loggers
    if (config.loggers) {
        el.className = "d-none";
        sal.className = "d-block";
    } else {
        el.className = "d-block";
        sal.className = "d-none";
    }
    return new_fields;
}


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
                var nf = status_cruise_definition(timestamp, values);
                for (var key in nf) {
                    new_fields[key] = nf[key];
                }
                break;

            // Cruise Mode update
            case 'status:cruise_mode':
                if (timestamp < global_last_cruise_timestamp) {
                    break;
                }
                global_last_cruise_timestamp = timestamp;
                update_cruise_mode(timestamp, values);
                break;

            // Logger Status update
            case 'status:logger_status':
                if (timestamp < global_last_logger_status_timestamp) {
                    break;
                }
                global_last_logger_status_timestamp = timestamp;
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

////////////////////////////
// Process a cruise_definition update
function update_cruise_definition(timestamp, cruise_definition) {
    // Utility function used to determine if we need to update
    // console.log("update_cruise_def: ", JSON.stringify(cruise_definition))
    // FIXME:  Set()? Return a diff: (added, removed) = diff(a, b)
    function array_keys_match(a, b) {
        if (Object.keys(a).length != Object.keys(b).length) {
            return false;
        }
        for (var key in a) {
            if (b[key] == undefined) {
                return false;
            }  
        }
        return true;
    }

    // Make sure this definition has all the parts we need
    if (!cruise_definition.modes) {
        console.log('Cruise definition has no modes - ignoring.');
        return {};
    }
    if (!cruise_definition.active_mode) {
        console.log('Cruise definition has no active mode - ignoring.');
        return {};
    }
    if (!cruise_definition.loggers) {
        console.log('Cruise definition has no loggers - ignoring.');
        return {};
    }
    // make cruise_definition available globally
    odas.cruise_definition = cruise_definition;

  ////////////////////////////////
  // Update the cruise id and filename
  //document.getElementById('cruise_id').innerHTML = cruise_definition.cruise_id;

    // update cruise name on navbar
    // FIXME:  this should be a dropdown with "reload/load/etc"
    if (cruise_definition.cruise_id) {
        var el = document.getElementById('cruise_id');
        if (el) {
            txtNode = el.childNodes[0];
            txtNode.nodeValue = cruise_definition.cruise_id;
            // Add tooltip with definition file name
            // cruise_definition.filename
            
        }
        el = document.getElementById('conf_file');
        if (el) {
            el.innerHTML = cruise_definition.filename;
        }
    }  

    ////////////////////////////////
    // Now update the cruise modes
    // var modes = cruise_definition.modes;
    //cruise_mode.update(global_active_mode);
    //global_active_mode = cruise_definition.active_mode;
    //var mode_button = document.getElementById('mode_button');
    //mode_button.innerHTML = global_active_mode;

    ////////////////////////////////
    // Now update loggers
    var loggers = cruise_definition.loggers;

    // Has the actual list of loggers changed? If not, only update
    // what has changed.
    if (array_keys_match(global_loggers, loggers)) {
        for (var logger_name in loggers) {
//            var button = document.getElementById(logger_name + '_config_button');
            var button = document.getElementById(logger_name + '_btn');
            button.innerHTML = loggers[logger_name].active;
        }
        return {};
    } // what do we do if they haven't changed?

    // If stuff has gotten updated, need to update CDS fields to
    // subscribe to.
    var new_fields = {};

    // Update logger_manager status, resubscribe to updates asking for greater
    // of last hour of records or last 100 records.
    cruise_mode.update(global_active_mode);
    // var button = document.getElementById('logger_manager_mode_button');
    //button.innerHTML = global_active_mode;
    new_fields['stderr:logger_manager'] = {'seconds':60*60, 'back_records':100};

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
    global_loggers = loggers;
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
        var time_window = {'seconds':1*60*60, 'back_records': 100};
        new_fields[name] = time_window;
        new_fields['stderr:logger:' + logger_name] = {'seconds':6*60*60, 'back_records': 100};
    }
    console.debug('Loaded new cruise.');
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
    return new_fields; // why?
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

