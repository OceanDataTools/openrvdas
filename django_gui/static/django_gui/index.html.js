//////////////////////////////////////////////////////////////////////////////
// Javascript behind and specific to the index.html page.
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

var global_loggers = {};
var global_active_mode = 'off';
var global_last_cruise_timestamp = 0;
var global_last_cruise_mode_timestamp = 0;
var global_last_logger_status_timestamp = 0;

////////////////////////////
function initial_send_message() {
  // Subscribing with seconds:-1 means we'll always start by getting
  // the most recent value, then all subsequent ones.
  return {'type':'subscribe',
          'fields': {
            'status:cruise_definition':{'seconds':-1},
            'status:cruise_mode':{'seconds':-1},
            'status:logger_status':{'seconds':-1},
            'status:file_update':{'seconds':0},

            // Get logger manager stderr, too.
            'stderr:logger_manager':{'seconds': 60*60}
            }
         }
}

////////////////////////////
function process_message(message_str) {
  reset_server_timeout(); // We've gotten a server update

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
      } else {
        //console.log('Subscribe request successful');
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
function array_keys_match(array_1, array_2) {
  if (Object.keys(array_1).length != Object.keys(array_2).length) {
    return false;
  }
  for (var key in array_1) {
    if (array_2[key] == undefined) {
      return false;
    }
  }
  return true;
}

////////////////////////////
// We've got data fields - process and put them where they belong in
// the HTML...
function process_data_message(message) {
  //console.log('Got new data message: ' + JSON.stringify(message));

  // We expect to receive a field dict, format:
  // {
  //   'data_id': ...,  # optional
  //   'fields': {
  //      field_name: [(timestamp, value), (timestamp, value),...],
  //      field_name: [(timestamp, value), (timestamp, value),...],
  //      ...
  //   }
  // }
  var new_fields = {};

  for (var field_name in message) {
    var value_list = message[field_name];
    switch (field_name) {
    //////////////////
    // If we've got a cruise definition update
    case 'status:cruise_definition':
      // Get the (timestamp, value) pair at end of list - that should
      // be the most recent.
      var [timestamp, cruise_definition] = value_list[value_list.length-1];

      //console.log('cruise_definition: ' + JSON.stringify(cruise_definition));
      if (timestamp > global_last_cruise_timestamp) {
        global_last_cruise_timestamp = timestamp;
        new_fields = update_cruise_definition(timestamp, cruise_definition);
      }
      break;

    //////////////////
    // If we've got a cruise mode update.  Again, look for (only)
    // the most recent.
    case 'status:cruise_mode':
      var [timestamp, cruise_mode] = value_list[value_list.length-1];

      //console.log('cruise_mode: ' + JSON.stringify(cruise_mode));
      if (timestamp > global_last_cruise_mode_timestamp) {
        global_last_cruise_mode_timestamp = timestamp;
        update_cruise_mode(timestamp, cruise_mode);
      }
      break;

    //////////////////
    // If we've got a logger status update.  Again, look for (only)
    // the most recent.
    case 'status:logger_status':
      var [timestamp, logger_status] = value_list[value_list.length-1];

      //console.log('logger_status: ' + JSON.stringify(logger_status));
      if (timestamp > global_last_logger_status_timestamp) {
        global_last_logger_status_timestamp = timestamp;
        update_logger_status(timestamp, logger_status);
      }
      break;

    //////////////////
    // The file from which our definition came has been updated. Make
    // the section that offers to reload it visible. If user is not
    // authenticated, this element will not exist.
    case 'status:file_update':
      var reload_span = document.getElementById('reload_span');
      if (reload_span) { reload_span.style.display = 'inline' }
      break;

    case 'stderr:logger_manager':
      process_stderr_message('logger_manager_stderr', value_list);
      break;

    ////////////////////////////////////////////////////
    // If something else, see if it's a logger status update
    default:
      var LOGGER_STDERR_PREFIX = 'stderr:logger:';
      if (field_name.indexOf(LOGGER_STDERR_PREFIX) == 0) {
        var logger_name = field_name.substr(LOGGER_STDERR_PREFIX.length);
        // Defined in stderr_log_utils.js
        process_stderr_message(logger_name + '_stderr', value_list);
      }
    }
  }

  //////////////////
  // Finally: Do we have new field subscriptions? Create the
  // subscription request.  But make sure we keep listening for future
  // logger_list, mode_list mode updates.
  if (Object.keys(new_fields).length) {
    new_fields['status:cruise_definition'] = {'seconds':-1};
    new_fields['status:cruise_mode'] = {'seconds':-1};
    new_fields['status:logger_status'] = {'seconds':-1};
    new_fields['status:file_update'] = {'seconds':0};
    var subscribe_message = {'type':'subscribe', 'fields':new_fields};
    send(subscribe_message);
  }
}

////////////////////////////
// Process a cruise_definition update
function update_cruise_definition(timestamp, cruise_definition) {
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

  ////////////////////////////////
  // Update the cruise id and filename
  document.getElementById('cruise_id').innerHTML = cruise_definition.cruise_id;
  document.getElementById('filename').innerHTML = cruise_definition.filename;

  ////////////////////////////////
  // Now update the cruise modes
  var modes = cruise_definition.modes;
  global_active_mode = cruise_definition.active_mode;
  var mode_button = document.getElementById('logger_manager_mode_button');
  mode_button.innerHTML = global_active_mode;

  ////////////////////////////////
  // Now update loggers
  var loggers = cruise_definition.loggers;

  // Has the actual list of loggers changed? If not, only update
  // what has changed.
  if (array_keys_match(global_loggers, loggers)) {
    for (var logger_name in loggers) {
      var button = document.getElementById(logger_name + '_config_button');
      button.innerHTML = loggers[logger_name].active;
    }
    return {};
  }

  // If stuff has gotten updated, need to update CDS fields to
  // subscribe to.
  var new_fields = {};

  // Update logger_manager status, resubscribe to updates asking for greater
  // of last hour of records or last 100 records.
  var button = document.getElementById('logger_manager_mode_button');
  button.innerHTML = global_active_mode;
  new_fields['stderr:logger_manager'] = {'seconds':60*60, 'back_records':100};

  ////////////////////////////////
  // If the list of loggers has changed, we need to rebuild the
  // list. Begin by emptying out table rows except for header row.
  var table = document.getElementById('logger_table_body');
  var row_count = table.rows.length;
  var keep_first_num_rows = 3;
  for (var i = keep_first_num_rows; i < row_count; i++) {
    table.deleteRow(keep_first_num_rows);
  }

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
    config_td.setAttribute('style', 'height:30px;width:75px;');

    var button = document.createElement('button');
    button.setAttribute('id', logger_name + '_config_button');
    button.setAttribute('type', 'submit');
    button.innerHTML = logger.active;

    button.setAttribute('onclick',
                        'open_edit_config(event, \'' + logger_name + '\')');
    config_td.appendChild(button);
    tr.appendChild(config_td);

    var stderr_td = document.createElement('td');
    var stderr_div = document.createElement('div');

    stderr_div.setAttribute('id', logger_name + '_stderr');
    stderr_div.setAttribute('style', 'height:30px;width:450px;background-color:white;padding:0px;overflow-y:auto;resize:both;');
    stderr_div.style.fontSize = 'x-small';
    stderr_td.appendChild(stderr_div);
    tr.appendChild(stderr_td);
    table.appendChild(tr);

    // Also, since we now have a new logger, we'll want to subscribe
    // to stderr updates for it. Seed each logger window with at greater of
    // one hour of past log messages or most recent 100 messages.
    new_fields['stderr:logger:' + logger_name] = {'seconds':60*60, 'back_records': 100};
  }
  console.log('Loaded new cruise.');
  //console.log('New fields are: ' + JSON.stringify(new_fields));
  return new_fields;
}

////////////////////////////
// Process a cruise_mode update
function update_cruise_mode(timestamp, cruise_mode) {
  var new_mode = cruise_mode.active_mode;
  global_active_mode = new_mode;
  var mode_button = document.getElementById('logger_manager_mode_button');
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
function update_logger_status(timestamp, logger_status) {
  reset_status_timeout(); // We've gotten a status update

  if (!logger_status || Object.keys(logger_status).length === 0) {
      return;
  }
  // Display logger section, if it's not already showing
  // TODO: optimize this so we don't do it every time.
  document.getElementById('empty_loggers').style.display = 'none';
  document.getElementById('status_and_loggers').style.display = 'block';

  if (timestamp < global_last_logger_status_timestamp) {
    // We've already seen this logger status or a more recent
    // one. Ignore it.
    console.log('Got stale logger status - skipping...');
    return;
  }
  global_last_logger_status_timestamp = timestamp;

  for (var logger_name in logger_status) {
    var status = logger_status[logger_name];
    var button = document.getElementById(logger_name + '_config_button');
    if (button == undefined) {
      continue;
    }
    button.innerHTML = status.config;
    if (status.status == 'RUNNING') {
      button.style.backgroundColor = "lightgreen";
    } else if (status.status == 'EXITED') {
      button.style.backgroundColor = "lightgray";
    } else if (status.status == "STARTING") {
      button.style.backgroundColor = "khaki";
    } else if (status.status == "BACKOFF") {
      button.style.backgroundColor = "gold";
    } else if (status.status == 'FATAL') {
      button.style.backgroundColor = "red";
    } else {
      button.style.backgroundColor = "white";
    }
  }
}

////////////////////////////
// Helper function: Does the line in question look like a logging
// line? That is, does it begin with a date string?
function looks_like_log_line(line) {
  return (typeof line == 'string' && Date.parse(line.split('T')[0]) > 0);
}

////////////////////////////////////////////////////////////////////////////////
var NOW_TIMEOUT_INTERVAL = 1000;     // Update console clock every second
var SERVER_TIMEOUT_INTERVAL = 5000;  // 5 seconds before warn about server
var STATUS_TIMEOUT_INTERVAL = 10000; // 10 seconds before warn about status

///////////////////////////////
function date_str() {
  return Date().substring(0,24);
}

///////////////////////////////
// Timer to update the 'Now' clock on web console.
function flag_now_timeout() {
  document.getElementById('time_td').innerHTML = date_str();
  clearInterval(now_timeout_timer);
  now_timeout_timer = setInterval(flag_now_timeout, NOW_TIMEOUT_INTERVAL);
}

///////////////////////////////
// Timer to check how long it's been since our last status update. If
// no update in N seconds, change status background color to yellow, and
// flag all loggers in yellow to show that we're not confident of
// their state.
function flag_status_timeout() {
  document.getElementById('status_time_td').style.backgroundColor ='yellow';
  for (var logger in global_loggers) {
    var config_button = document.getElementById(logger + '_config_button');
    if (config_button) {
      config_button.style.backgroundColor = 'yellow';
    } else {
      console.log('Couldnt find logger ' + logger);
    }
  }
}
function reset_status_timeout() {
  var now = date_str();
  document.getElementById('time_td').innerHTML = now;
  var status_time_td = document.getElementById('status_time_td');
  status_time_td.innerHTML = now;
  status_time_td.style.backgroundColor = 'white';
  clearInterval(status_timeout_timer);
  status_timeout_timer = setInterval(flag_status_timeout,
                                     STATUS_TIMEOUT_INTERVAL);
}

///////////////////////////////
// Timer to check how long it's been since our last update of any kind
// from the data server. If no update in 5 seconds, change background
// color to yellow
function flag_server_timeout() {
  document.getElementById('server_time_td').style.backgroundColor ='yellow';
}
function reset_server_timeout() {
  var now = date_str();
  document.getElementById('time_td').innerHTML = now;
  var status_time_td = document.getElementById('server_time_td');
  status_time_td.innerHTML = now;
  status_time_td.style.backgroundColor = 'white';
  clearInterval(server_timeout_timer);
  server_timeout_timer = setInterval(flag_server_timeout,
                                     SERVER_TIMEOUT_INTERVAL);
}

///////////////////////////////
// Start the timers
var now_timeout_timer = setInterval(flag_now_timeout, NOW_TIMEOUT_INTERVAL);
var status_timeout_timer = setInterval(flag_status_timeout,
                                       STATUS_TIMEOUT_INTERVAL);
var server_timeout_timer = setInterval(flag_server_timeout,
                                       SERVER_TIMEOUT_INTERVAL);

///////////////////////////////
// Turn select pull-down's text background yellow when it's been changed
var manually_selected_mode = null;

///////////////////////////////
function message_window() {
  var path = '/server_messages/20/';
  window.open(path, '_blank',
  'height=350,width=540,toolbar=no,location=no,directories=no,status=no,menubar=no,scrollbars=yes,copyhistory=no');
}

///////////////////////////////
// When user clicks a logger config button.
function open_change_mode(click_event) {
  if (!click_event) click_event = window.event;
  var window_args = [
    'titlebar=no',
    'location=no',
    'height=320',
    'width=800',
    'top=' + click_event.clientY,
    'left=' + (click_event.clientX + 520),
    'scrollbars=yes',
    'status=no'
  ];
  window.open('../change_mode/', '_blank', window_args.join());
}

///////////////////////////////
// When user clicks a logger config button.
function open_edit_config(click_event, logger_name) {
  if (!click_event) click_event = window.event;
  var window_args = [
    'titlebar=no',
    'location=no',
    'height=320',
    'width=720',
    'top=' + click_event.clientY,
    'left=' + (click_event.clientX + 520),
    'scrollbars=yes',
    'status=no'
  ];
  window.open('../edit_config/' + logger_name, '_blank', window_args.join());
}

///////////////////////////////
// When user clicks the Load new definition button.
function open_load_definition(click_event) {
  if (!click_event) click_event = window.event;
  var window_args = [
    'titlebar=no',
    'location=no',
    'height=320',
    'width=370',
    'top=' + click_event.clientY,
    'left=' + (click_event.clientX + 520),
    'scrollbars=yes',
    'status=no'
  ];
  window.open('../choose_file/', '_blank', window_args.join());
}
