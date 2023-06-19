///////////////////////////////////////////////////////////////////////////////
// Javascript for 'index.html'
//
// Typical invocation will look like:
//    <script src="/static/django_gui/index.html.js"></script>
//    <script src="/static/django_gui/websocket.js"></script>
//
//
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

    var t = 1000;

    function update_now() {
        if (!el) { return; }
        el.innerHTML = Date().substring(0, 24);
    }
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
    var el = document.getElementById('status_time_td');
    el.setAttribute('data-bs-toggle', 'tooltip');
    el.setAttribute('data-bs-placement', 'top');
    el.setAttribute('title', 'Last status update from LoggerManager');
    if (el) {
        el.className = '';
    }

    // Default timeout 10 seconds, over-ride by config
    var o = window.odas || {};
    var oT = o.Timeouts || {};
    var timeout_ms = oT.Status * 1000 || 10000;
    var timer = setTimeout(timed_out, timeout_ms);

    function timed_out() {
        if (el) {
            el.className = 'text-danger';
        }
    }

    var update = function() {
        clearTimeout(timer);
        timer = setTimeout(timed_out, timeout_ms);
        if (el) {
            el.innerHTML = Date().substring(0,24);
            el.className = '';
        }
    };

    return {
        update: update
    };
})();

////////////////////////////////////////////////////////////////////
//
//  Handle the updates of the server_time_td
//
////////////////////////////////////////////////////////////////////
var server_td = (function() {
    var el = document.getElementById('server_time_td');
    el.setAttribute('data-bs-toggle', 'tooltip');
    el.setAttribute('data-bs-placement', 'top');
    el.setAttribute('title', 'Last communication from CDS');
    el.className = '';

    // Default timeout 5 seconds, over-ride by config
    // use error-less fallback in case config not loaded
    var o = odas || {};
    var oT = o.Timeouts || {};
    var timeout_ms = oT.Server * 1000 || 5000;
    var timer = setTimeout(timed_out, timeout_ms);

    function timed_out() {
        if (el) {
            el.className = 'text-danger';
        }
    }

    var update = function() {
        clearTimeout(timer);
        timer = setTimeout(timed_out, timeout_ms);
        if (el) {
            el.innerHTML = Date().substring(0, 24);
            el.className = '';
        }
    };

    return {
        update: update
    };
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
        iziToast.warning({
            title: 'Error from Cached Data Server',
            message: message_str,
        });
        //console.warn('Error from server: ' + message_str);
        return;
    }

    // Now go through all the types of messages we know about and
    // deal with them.
    switch (message.type) {
        case 'data':
            process_data_message(message.data);
            break;
        case 'subscribe':
            break;
        case undefined:
            Q = "Error: meesage has no type field:";
            iziToast.warning({
                title: 'CDS message has no type field',
                message: message_str,
            });
            break;
        default:
            Q = "Error: unknown message type";
            iziToast.warning({
                title: 'CDS message has unknown type',
                message: Q,
            });
    }
}

// WOW!!  Lots and lots of code here.  Any way to make this
//        *less* code?
var CruiseDef = (function() {
    var our_timestamp = 0;
    var el_empty =  document.getElementById('empty_loggers');
    var el_populated = document.getElementById('status_and_loggers');
    var loggers = {};

    function diff_loggers(config_loggers) {
        var new_loggers = [];   // new loggers we don't have
        var old_loggers = [];    // loggers we had that are gone

        // Hmmm. performance wise, it is faster to do it this way?
        var new_set = new Set(Object.keys(config_loggers));
        var old_set = new Set(Object.keys(loggers));

        for (var logger of new_set) {
            if (!old_set.has(logger)) {
                new_loggers.push(logger);
            }
        }
        for (logger of old_set) {
            if (!new_set.has(logger)) {
                old_loggers.push(logger);
            }
        }
        return {
            new: new_loggers,
            old: old_loggers,
            size: new_loggers.length + old_loggers.length,
        };
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
            var txtNode = el.childNodes[0];
            txtNode.nodeValue = cruise_id;
        }
        el = document.getElementById('reload_config_link');
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
        // Ensure all the correct parts are there
        // The API sorts these, but the code exists in the Django
        // GUI, supposedly for a reason....
        var keys = ['modes', 'active_mode', 'loggers'];
        for (var index in keys) {
            if (keys[index] in config) {
                continue;
            }
            msg = 'Cruise def has no ' + keys[index] + ' - ignoring.';
            console.warn(msg);
            return;
        }
        // we always get two messages at page startup.  This is a hack
        // to not report on the first one.
        if (odas.api) {
            iziToast.success({
                title: 'Loaded new configuration file',
                message: config.filename,
            });
        }
        // console.info('Loaded new configuration');
        odas.api = config;
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
        var logger_name;
        if (diff.size == 0) {
           // Set the logger button texts
           for (logger_name in loggers) {
               var mode = loggers[logger_name].active;
               LoggerButton.mode_update(logger_name, mode);
           }
           return {};
        } else {
           update_logger_rows(loggers);
        }
        // If stuff has gotten updated, need to update CDS fields to
        // subscribe to.

        var new_fields = {};

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
        for (logger_name in loggers) {
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
            stderr_div.addEventListener('contextmenu', STDERR.ctxmenu);
            stderr_td.appendChild(stderr_div);
            tr.appendChild(stderr_td);
            table.appendChild(tr);

            // Also, since we now have a new logger, we'll want to
            // subscribe to stderr updates for it.  Send each logger
            // window with at greatest of one hour past log messges or
            // most recent 100 messages
            var name = 'stderr:logger:' + logger_name;
            var time_window = {'seconds':6*60*60, 'back_records': 100};
            new_fields[name] = time_window;
            new_fields['stderr:logger:' + logger_name] = time_window;
        }

        if (Object.keys(new_fields).length) {
            var time_window = {'seconds':1*60*60, 'back_records': 100};
            new_fields['stderr:logger_manager'] = time_window;
            new_fields['status:cruise_definition'] = {'seconds':-1};
            new_fields['status:cruise_mode'] = {'seconds':-1};
            new_fields['status:logger_status'] = {'seconds':-1};
            new_fields['status:file_update'] = {'seconds':0};
            var subscribe_message = {'type':'subscribe', 'fields':new_fields};
            WS.write(subscribe_message);
        }
    };
        

    return {
        status_message: status_message,
    };   

})()

////////////////////////////
////////////////////////////
// We've got data fields - process and put them where they belong in
// the HTML...
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
  
    for (var field_name in message) {
        // If we receive a status update, update the status time
        if (field_name.startsWith('status:')) {
            status_td.update();
        }
        var value_list = message[field_name];
        // Get the [timestamp, value] pair at the end of the list.
        // That should be the most recent.
        var [ timestamp, values ] = value_list.pop();
        switch (field_name) {
            // Cruise definition updatee
            case 'status:cruise_definition':
                CruiseDef.status_message(timestamp, values);
                break;

            // Cruise Mode update
            case 'status:cruise_mode':
                cruise_mode.status_update(timestamp, values);
                break;

            // Logger Status update
            case 'status:logger_status':
                LoggerButton.update(timestamp, values);
                break;

            //////////////////
            // The file from which our definition came has been updated. Make
            // the section that offers to reload it visible. If user is not
            // authenticated, this element will not exist.
            // File_update update
            case 'status:file_update':
               var o = odas || {};
               var oA = o.api || {};
               config_timestamp = oA.config_timestamp || 0;
               var staleSpan = document.getElementById('stale_span');
               if (! staleSpan) { return; }
               if (values > config_timestamp) {
                       staleSpan.classList.remove('d-none');
               } else {
                       staleSpan.classList.add('d-none');
               }
               break;

            case 'stderr:logger_manager':
                STDERR.process('logger_manager_stderr', value_list);
                break;

            ////////////////////////////////////////////////////
            // If something else, see if it's a logger status update
            default:
                var LOGGER_STDERR_PREFIX = 'stderr:logger:';
                if (field_name.startsWith(LOGGER_STDERR_PREFIX)) {
                    var logger_name = field_name.split(':')[2];
                    // Defined in stderr_log_utils.js
                    var target = logger_name + '_stderr';
                    STDERR.process(target, value_list);
                }
        }

    }
}


var cruise_mode = (function() {
    // Methods should be:
    //     CreateButton (construct button, attach events)
    //     ButtonPresseda(show modal)
    //     status_update(message from CDS)
    //     update(mode)
    var mode_button = document.getElementById('mode_button');
    var active_mode = 'off';
    var status_timestamp = 0;

    function init() {
        // attach events to the button ??  Handle Modal here?
    }

    function status_update(timestamp, values) {
        if (timestamp < status_timestamp) {
            console.debug("Stale status:cruise_mode message");
            return;
        }
        status_timestamp = timestamp;
        if (values.active_mode != active_mode) {
            update(values.active_mode);
        }
    }

    // Called when we get a message saying the mode has changed
    // This method also called directly when cruise config is updated
    function update(new_mode) {
        active_mode = new_mode;
        if (mode_button) {
            mode_button.innerHTML = new_mode;
        }
    }

    // not called anywhere, but...
    function get_mode() {
        return active_mode;
    }

    init();

    return {
        update: update,
        get_mode: get_mode,
        status_update: status_update,
    };
})();

