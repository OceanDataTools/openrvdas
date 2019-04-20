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

var loggers = null;     // to contain assoc array of logger_name -> true
var logger_status = {}; // to contain configs=list, current_config, running 
var modes = null;
var current_mode = null;

////////////////////////////
function initial_send_message() {
  return {'type':'subscribe',
          'fields': {'status:cruise_id':{'seconds':-1},
                     'status:logger_list':{'seconds':-1},
                     'status:mode_list':{'seconds':-1},
                     'status:mode':{'seconds':-1}}
         }
}

////////////////////////////
function process_message(message_str) {
  // Just for debugging purposes
  var message = JSON.parse(message_str);

  // Update time string and reset timeout timer
  document.getElementById('time_td').innerHTML = Date();
  document.getElementById('time_warning_row').style.display = 'none';
  document.getElementById('time_row').style.backgroundColor = 'white';
  //document.getElementById('time_str').innerHTML = message.time_str;
  //time_str.style.backgroundColor = 'white';
  clearInterval(timeout_timer);
  timeout_timer = setInterval(flag_timeout, TIMEOUT_INTERVAL);

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
// We've got data fields - process and put them where they belong in
// the HTML...
function process_data_message(data_dict) {
  var data_str = JSON.stringify(data_dict);
  var new_fields = {};

  for (var field_name in data_dict) {
    var value_list = data_dict[field_name];
    switch (field_name) {
      ////////////////////////////////////////////////////
      // If we've got a new list of loggers; rebuild assoc array
      case 'status:cruise_id':
        var cruise_id = value_list[value_list.length-1][1];
        document.getElementById('cruise_id').innerHTML = cruise_id;
        break;

      ////////////////////////////////////////////////////
      // If we've got a new list of loggers; rebuild assoc array
      // subscribing to their status and their stderr outputs.
      case 'status:logger_list':
        loggers = {};
        var logger_list = value_list[value_list.length-1][1];
        for (var ll_i = 0; ll_i < logger_list.length; ll_i++) {
          var logger = logger_list[ll_i];
          loggers[logger] = true;
          new_fields['status:logger:' + logger] = {'seconds':-1};
          new_fields['stderr:logger:' + logger] = {'seconds':88000};
        }
        update_logger_list();
        break;

      ////////////////////////////////////////////////////
      // If we've got a new list of modes
      case 'status:mode_list':
        modes = value_list[value_list.length-1][1];
        update_modes();
        break;

      ////////////////////////////////////////////////////
      // If we've got a new mode
      case 'status:mode':
        current_mode = value_list[value_list.length-1][1];
        update_modes();
        break;

      ////////////////////////////////////////////////////
      // If something else, see if it's a logger status update
      default:
        // Is this field a logger status?
        var logger_status_prefix = 'status:logger:';
        var logger_stderr_prefix = 'stderr:logger:';
      
        if (field_name.indexOf(logger_status_prefix) == 0) {
          var logger = field_name.substr(logger_status_prefix.length);
          if (loggers[logger] == undefined) {
            console.log('Got status for unknown logger: ' + logger);
            continue;
          }
          // Get last (timestamp, status) pair, and keep the status
          logger_status[logger] = value_list[value_list.length-1][1];
          update_logger(logger);
        }
        else if (field_name.indexOf(logger_stderr_prefix) == 0) {
          var logger = field_name.substr(logger_stderr_prefix.length);
          if (loggers[logger] == undefined) {
            console.log('Got sterr for unknown logger: ' + logger);
            continue;
          }
          // Pass all (timestamp, stderr_mesg) pairs in list to updater
          update_logger_stderr(logger, value_list)
        }
        else {
          console.log('Unhandled field_name: ' + field_name);
        }
    }
  }
  // Do we have new field subscriptions? Create the subscription request.
  // But make sure we keep listening for future logger_list, mode_list
  // mode updates.
  if (Object.keys(new_fields).length) {
    new_fields['status:cruise_id'] = {'seconds':0};
    new_fields['status:logger_list'] = {'seconds':0};
    new_fields['status:mode_list'] = {'seconds':0};
    new_fields['status:mode'] = {'seconds':0};

    var subscribe_message = {'type':'subscribe', 'fields':new_fields};
    send(subscribe_message);
  }
}

////////////////////////////
// Update HTML for logger list.
function update_logger_list() {
  console.log('Updating logger list with: '
              + JSON.stringify(Object.keys(loggers)));
  var table = document.getElementById('logger_table_body');

  // Empty out table rows except for header row
  var row_count = table.rows.length;
  var keep_first_num_rows = 1;
  for (var i = keep_first_num_rows; i < row_count; i++) {
    table.deleteRow(keep_first_num_rows);
  }
  // Create one row for each new logger
  for (logger in loggers) {
    //console.log('Adding row for ' + logger);
    // table row creation
    var tr = document.createElement('tr');
    tr.setAttribute('id', logger + '_row');

    var name_td = document.createElement('td');
    name_td.setAttribute('id', logger + '_td');
    tr.appendChild(name_td);

    var config_td = document.createElement('td');
    config_td.setAttribute('id', logger + '_config_td');

    var button = document.createElement('button');
    button.setAttribute('id', logger + '_config_button');
    button.setAttribute('type', 'submit');

    // Disable if user is not authenticated
    if (! USER_AUTHENTICATED) {
      button.setAttribute('disabled', true);
    }

    button.setAttribute('onclick', 'button_clicked(\'' + logger + '\')');
    config_td.appendChild(button);
    tr.appendChild(config_td);

    var error_td = document.createElement('td');
    error_td.setAttribute('id', logger + '_error');
    error_td.setAttribute('style', 'min-width:0px;padding:0px;overflow:auto;');
    error_td.style.fontSize = 'small';
    tr.appendChild(error_td);

    table.appendChild(tr);

    // Now fill in whatever is supposed to be on that row
    update_logger(logger);                                   
  }
  // We may not have had a configuration loaded before, and if not, our
  // whole logger table may still be hidden. Set it to be visible now.
  document.getElementById('config_loaded').style.display = 'block';
}

////////////////////////////
// Update HTML for single logger
function update_logger(logger) {
  var status = logger_status[logger];
  //console.log('  Updating logger ' + logger + '; status: '
  //            + JSON.stringify(status));
  var name_td = document.getElementById(logger + '_td');
  name_td.innerHTML = logger;

  // If no status, create a dummy for it so we can get (undefined) properties
  if (status == undefined) {
    status = true;
  }
  var config_button = document.getElementById(logger + '_config_button');
  config_button.innerHTML = status.config;

  // Got a ternary status for this logger:
  //   true:  we're running and are supposed to be
  //   false: not running and are supposed to be
  //   null:  not running and not supposed to be
  var button_color = (status.running == true ? 'lightgreen' :
                      (status.running == false ? 'orangered' : 'lightgray'));
  config_button.style.backgroundColor = button_color;
}

////////////////////////////
// Update stderr for a logger - append new messages
function update_logger_stderr(logger, stderr_list) {
  var error_td = document.getElementById(logger + '_error');
  var logger_stderr = error_td.innerHTML;
  console.log('updating stderr for ' + logger);
  for (s_i = 0; s_i < stderr_list.length; s_i++) {
    var pair = stderr_list[s_i];
    var ts = pair[0];
    var mesg = pair[1];
    console.log('  message: ' + mesg);
    if (logger_stderr) {
      logger_stderr += '<br>\n';
    }
    logger_stderr += mesg;
  }
  error_td.innerHTML = logger_stderr;
}

////////////////////////////
// Update HTML for modes
function update_modes() {
  console.log('Updating modes: ' + modes + ' (current: ' + current_mode + ')');

  var mode_selector = document.getElementById('select_mode');
  mode_selector.setAttribute('onchange', 'highlight_select_mode()');

  // Remove all old options
  while (mode_selector.length) {
    mode_selector.remove(0);
  }
  // Add new ones
  for (m_i = 0; m_i < modes.length; m_i++) {
    var mode_name = modes[m_i];
    var opt = document.createElement('option');
    opt.setAttribute('id', 'mode_' + mode_name);
    opt.innerHTML = mode_name;
    if (mode_name == current_mode) {
      opt.setAttribute('selected', true);
    }
    mode_selector.appendChild(opt);
  }
}

///////////////////////////////
// Run timer to check how long it's been since our last update. If no
// update in 5 seconds, change background color to red
var TIMEOUT_INTERVAL = 5000;
function flag_timeout() {
  document.getElementById('time_row').style.backgroundColor = 'orangered';
  document.getElementById('time_warning_td').innerHTML = Date();
}
var timeout_timer = setInterval(flag_timeout, TIMEOUT_INTERVAL);

///////////////////////////////
// Turn select pull-down's text background yellow when it's been changed
function highlight_select_mode() {
  var mode_selector = document.getElementById('select_mode');
  var selected_mode = mode_selector.options[mode_selector.selectedIndex].text;
  var new_color = (selected_mode == current_mode ? 'white' : 'yellow');
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

