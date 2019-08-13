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
//    <script src="/static/django_gui/index.js"></script>
//    <script src="/static/django_gui/websocket.js"></script>
//
// Note that this also counts on variables USER_AUTHENTICATED and
// WEBSOCKET_SERVER being set in the calling page.

var global_loggers = {};
var global_active_mode = 'off';
var global_logger_stderr = {};
var global_last_cruise_timestamp = 0;
var global_last_logger_status_timestamp = 0;

////////////////////////////
function initial_send_message() {
  return {'type':'subscribe',
          'fields': {
            'status:cruise_definition':{'seconds':-1},
            'status:logger_status':{'seconds':-1}
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
function process_data_message(data_dict) {
  var data_str = JSON.stringify(data_dict);
  var new_fields = {};

  //console.log('Got new data message: ' + data_str);
  for (var field_name in data_dict) {
    var value = data_dict[field_name];
    switch (field_name) {
    ////////////////////////////////////////////////////
    // If we've got a cruise definition update
    case 'status:cruise_definition':
      // We will have been handed a list of [timestamp, cruise_definition]
      // pairs. Fetch the last cruise definition in the list.
      var cruise_timestamp = value[value.length-1][0];
      if (cruise_timestamp <= global_last_cruise_timestamp) {
        // We've already seen this cruise definition or a more recent
        // one. Ignore it.
        break;
      }
      global_last_cruise_timestamp = cruise_timestamp;
      var cruise_definition = value[value.length-1][1];

      // Make sure this definition has all the parts we need
      if (!cruise_definition.modes) {
        console.log('Cruise definition has no modes - ignoring.');
        break;
      }
      if (!cruise_definition.active_mode) {
        console.log('Cruise definition has no active mode - ignoring.');
        break;
      }
      if (!cruise_definition.loggers) {
        console.log('Cruise definition has no loggers - ignoring.');
        break;
      }

      ////////////////////////////////
      // Update the cruise id
      document.getElementById('cruise_id').innerHTML = cruise_definition['cruise_id'];

      ////////////////////////////////
      // Now update the cruise modes
      var modes = cruise_definition.modes;
      var active_mode = cruise_definition.active_mode;
      global_active_mode = active_mode;

      var mode_selector = document.getElementById('select_mode');
      mode_selector.setAttribute('onchange', 'highlight_select_mode()');

      // Remove all old mode options
      while (mode_selector.length) {
        mode_selector.remove(0);
      }
      // Add new ones
      for (m_i = 0; m_i < modes.length; m_i++) {
        var mode_name = modes[m_i];
        var opt = document.createElement('option');
        opt.setAttribute('id', 'mode_' + mode_name);
        opt.innerHTML = mode_name;
        if (mode_name == active_mode) {
          opt.setAttribute('selected', true);
        }
        mode_selector.appendChild(opt);
      }

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
        break;
      }

      ////////////////////////////////
      // If the list of loggers has changed, we need to rebuild the
      // list. Begin by emptying out table rows except for header row.
      var table = document.getElementById('logger_table_body');
      var row_count = table.rows.length;
      var keep_first_num_rows = 1;
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

        var name_td = document.createElement('td');
        name_td.setAttribute('id', logger_name + '_td');
        tr.appendChild(name_td);
        name_td.innerHTML = logger_name;

        var config_td = document.createElement('td');
        config_td.setAttribute('id', logger_name + '_config_td');

        var button = document.createElement('button');
        button.setAttribute('id', logger_name + '_config_button');
        button.setAttribute('type', 'submit');
        button.innerHTML = logger.active;

        // Disable if user is not authenticated
        if (! USER_AUTHENTICATED) {
          button.setAttribute('disabled', true);
        }
        button.setAttribute('onclick',
                            'button_clicked(\'' + logger_name + '\')');
        config_td.appendChild(button);
        tr.appendChild(config_td);

        var stderr_td = document.createElement('td');
        var stderr_div = document.createElement('div');

        stderr_div.setAttribute('id', logger_name + '_stderr');
        stderr_div.setAttribute('style', 'height:30px;background-color:white;min-width:0px;padding:0px;overflow-y:auto;');
        stderr_div.style.fontSize = 'small';
        stderr_td.appendChild(stderr_div);
        tr.appendChild(stderr_td);
        table.appendChild(tr);

        // Also, since we now have a new logger, we'll want to subscribe
        // to stderr updates for it.
        new_fields['stderr:logger:' + logger_name] = {'seconds':88000};
      }

      break;

    ////////////////////////////////////////////////////
    // If we've got a logger status update; the values will be a list
    // of dicts where for each dict, the timestamp of the status is
    // the key, and the value is a dict of {logger_name:
    // logger_status}.

    case 'status:logger_status':
      //console.log('Got status update');
      reset_status_timeout(); // We've gotten a status update


      // The value array will be a list of [timestamp, status_update]
      // pairs. We want to grab the most recently-timestamped status update.
      var timestamp_status_array = value[value.length-1][1];

      // The status update will be an associative array of {timestamp:
      // {logger:status, logger:status,...}}.  Go through each
      // timestamp and update the loggers it references.
      for (var status_timestamp in timestamp_status_array) {
        var status_array = timestamp_status_array[status_timestamp];
        for (var logger_name in status_array) {
          var logger_status = status_array[logger_name];
          var button = document.getElementById(logger_name + '_config_button');
          if (button == undefined) {
            console.log('Button not found for logger ' + logger_name);
            continue;
          }
          button.innerHTML = logger_status.config;
          // Update status - status is ternary:
          //   true:  we're running and is supposed to be
          //   false: not running and is supposed to be
          //   null:  not running and not supposed to be
          if (logger_status.running == true) {
            button.style.backgroundColor = "lightgreen";
          } else if (logger_status.running == false) {
            button.style.backgroundColor = "orange";
          } else {
            button.style.backgroundColor = "lightgray";
          }
          if (logger_status.failed) {
            button.style.backgroundColor = "red";
          }
        }
      }
      break;

    ////////////////////////////////////////////////////
    // If something else, see if it's a logger status update
    default:
      var logger_stderr_prefix = 'stderr:logger:';

      if (field_name.indexOf(logger_stderr_prefix) == 0) {
        var logger_name = field_name.substr(logger_stderr_prefix.length);
        add_to_stderr(logger_name, value);
        continue;
      }
    }
  }
  // Do we have new field subscriptions? Create the subscription request.
  // But make sure we keep listening for future logger_list, mode_list
  // mode updates.
  if (Object.keys(new_fields).length) {
    new_fields['status:cruise_definition'] = {'seconds':-1};
    new_fields['status:logger_status'] = {'seconds':-1};

    var subscribe_message = {'type':'subscribe', 'fields':new_fields};
    send(subscribe_message);
  }
}

////////////////////////////
// Add the array of new (timestamped) messages to the stderr display
// for logger_name. Make sure messages are in order and unique.
function add_to_stderr(logger_name, new_messages) {
  //console.log('updating stderr for ' + logger_name + ': ' + new_messages);
  var stderr_messages = global_logger_stderr[logger_name] || [];

  // In case it's not sorted yet
  stderr_messages.sort();

  for (s_i = 0; s_i < new_messages.length; s_i++) {
    var pair = new_messages[s_i];
    var new_message = pair[1];

    if (stderr_messages.length == 0) {
      stderr_messages.push(new_message);
      continue;
    }

    // Insert new message (if unique)
    for (m_i = stderr_messages.length - 1; m_i >= 0; m_i--) {
      if (new_message == stderr_messages[m_i]) {
        break; // duplicate message - ignore it
      }
      else if (new_message > stderr_messages[m_i]) {
        stderr_messages.splice(m_i+1, 0, new_message);
        break;
      }
    }
  }
  // Fetch the element where we're going to put the messages
  var stderr_div = document.getElementById(logger_name + '_stderr');
  if (stderr_div == undefined) {
    console.log('Found no stderr div for logger ' + logger_name);
    return;
  }
  stderr_div.innerHTML = stderr_messages.join('<br>\n');
  stderr_div.scrollTop = stderr_div.scrollHeight;  // scroll to bottom
  global_logger_stderr[logger_name] = stderr_messages;
}

////////////////////////////////////////////////////////////////////////////////
var NOW_TIMEOUT_INTERVAL = 1000;     // Update console clock every second
var SERVER_TIMEOUT_INTERVAL = 5000;  // 5 seconds before warn about server
var STATUS_TIMEOUT_INTERVAL = 10000; // 10 seconds before warn about status

// Question on timer warnings: should we reserve space for the
// warnings (e.g. use the commented-out "visibility=hidden" style), or
// have them open up space when errors occur? For now, for
// compactness, going with the latter route.
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
  document.getElementById('status_time_td').style.backgroundColor ='yellow';
}
function reset_server_timeout() {
  var now = date_str();
  document.getElementById('time_td').innerHTML = now;
  var status_time_td = document.getElementById('status_time_td');
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
function highlight_select_mode() {
  var mode_selector = document.getElementById('select_mode');
  var selected_mode = mode_selector.options[mode_selector.selectedIndex].text;
  var new_color = (selected_mode == global_active_mode ? 'white' : 'yellow');
  document.getElementById('select_mode').style.backgroundColor = new_color;
}

///////////////////////////////
// When a config button is clicked, change its color and open a
// config window.
function button_clicked(logger) {
  var config_button = document.getElementById(logger + '_config_button');
  config_button.style.backgroundColor = 'yellow';
  window.open('../edit_config/' + logger,
              '_blank',
              'location=yes,height=180,width=520,scrollbars=yes,status=yes');
}

///////////////////////////////
function load_cruise() {
  var select = document.getElementById('select_cruise');
  var cruise = select.options[select.selectedIndex].value;
  console.log('Loading page: /cruise/' + cruise);
  history.pushState(cruise, cruise, '/cruise/' + cruise);
  window.location.assign('/cruise/' + cruise);
}

///////////////////////////////
// Toggle whether the cruise file selector is visible
function toggle_load_config_div() {
  var x = document.getElementById('load_div_button');
  var y = document.getElementById('load_config_div');
  if (x.style.display === 'none') {
      x.style.display = 'block';
      y.style.display = 'none';
  } else {
      x.style.display = 'none';
      y.style.display = 'block';
  }
}

///////////////////////////////
// When the cruise file selector has a file selected, show the
// 'load' button
function show_load_button(files) {
  var load_button_div = document.getElementById('load_button_div');
  if (files.length) {
    load_button_div.style.display = 'block';
  } else {
    load_button_div.style.display = 'none';
  }
}

///////////////////////////////
function message_window() {
  var path = '/server_messages/20/';
  window.open(path, '_blank',
  'height=350,width=540,toolbar=no,location=no,directories=no,status=no,menubar=no,scrollbars=yes,copyhistory=no');
}
