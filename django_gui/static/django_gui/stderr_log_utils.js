//////////////////////////////////////////////////////////////////////////////
// Javascript for fetching log lines whose data_id matches some data_id,
// such as 'stderr:logger:s330', and appending them to a specified target div.
//
// Typical invocation will look like:
//    <script src="/static/django_gui/stderr_log_utils.js"></script>
//    <script src="/static/django_gui/edit_config.html.js"></script>
//    <script src="/static/django_gui/websocket.js"></script>
//
// Will take lines whose id matches 'stderr:logger:gyr1' and append them
// to a div on the paged whose identity is 'gyr1_stderr'. Etc.

////////////////////////////
// Process CDS data message (hopefully) containing log lines and add
// to the div we've been passed. Expects STDERR_DIV_MAP to be defined
// as an associative array of {field_name: div}, where field_name is
// a match for, e.g. stderr.logger.s330, and div is the id of the page's
// div into which matching lines should be placed.
function process_stderr_message(target_div_id, log_line_list) {
  // target_div_id  - e.g. 's330_stderr
  // log_line_list  - should be [(timestamp, line), (timestamp, line),...],
  //                  where 'line' is the log message to be recorded.
  if (!log_line_list || log_line_list.length == 0) {
    return;
  }
  var new_log_lines = '';

  for (var list_i = 0; list_i < log_line_list.length; list_i++) {
    // Skip duplicate messages
    if (list_i > 0 && log_line_list[list_i] == log_line_list[list_i-1]) {
      continue;
    }
    var [timestamp, log_line] = log_line_list[list_i];

    // Clean up message and add to new_log_lines list
    log_line = log_line.replace('\n','<br>') + '<br>\n';
    new_log_lines += color_log_line(log_line);
  }

  // Once all log lines have been added, fetch the div where we're
  // going to put them, and add to bottom.
  if (new_log_lines.length > 0) {
    var target_div = document.getElementById(target_div_id);
    if (target_div) {
      target_div.innerHTML += new_log_lines;
      target_div.scrollTop = target_div.scrollHeight;  // scroll to bottom
    } else {
      console.log('Couldn\'t find div for ' + target_div_id);
    }
  }
}

// Add HTML coloring to message depending on log level
function color_log_line(message) {
  var color = '';
  if (message.indexOf(' 30 WARNING ') > 0) {
    color = '#e09100';
  } else if (message.indexOf(' 40 ERROR ') > 0) {
    color = 'orange';
  } else if (message.indexOf(' 50 CRITICAL ') > 0) {
    color = 'red';
  }
  if (color !== '') {
    message = '<span style="color:' + color + '">' + message + '</span>';
  }
  return message;
}
