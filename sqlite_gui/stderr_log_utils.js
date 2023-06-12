//////////////////////////////////////////////////////////////////////////////
// Javascript for fetching log lines whose data_id matches some data_id,
// such as 'stderr:logger:s330', and appending them to a specified target div.
//
// Typical invocation will look like:
//    <script src="/static/django_gui/stderr_log_utils.js"></script>
//    <script src="/static/django_gui/websocket.js"></script>
//
// Will take lines whose id matches 'stderr:logger:gyr1' and append them
// to a div on the paged whose identity is 'gyr1_stderr'. Etc.

////////////////////////////
// Process CDS data message (hopefully) containing log lines and add
// to the div we've been passed.

var STDERR = (function() {
    var loggers = {}

    // FIXME:  Move creating stderr windows here.
    // FIXME:  Keep track of errors for possible badges.

    // target  - e.g. 's330_stderr
    // lines  - should be [(timestamp, line), (timestamp, line),...],
    //                  where 'line' is the log message to be recorded.
    var process = function(target, lines) {
        // If nothing to log, go home
        if (!lines || lines.length == 0) {
            return;
        }
        var new_log_lines = '';
        for (var i = 0, j = lines.length ; i < j; i++) {
            if (i > 0 && lines[i] == lines[i - 1]) {
                continue;  // skip duplicate messages
            }
            var [timestamp, log_line] = lines[i];

            // Clean up message and add to new_log_lines list
            log_line = log_line.replace(/\n$/, '');
            log_line = log_line.replace('\n', '<br />');
            new_log_lines += color_log_line(log_line, target);
        }

        // Once all log lines have been added, fetch the div where we're
        // going to put them, and add to bottom.
        if (new_log_lines.length > 0) {
            var target_div = document.getElementById(target);
            if (!target_div) {
                console.warn ('Couldn\'t find div for ' + target);
                return;
            }
            target_div.innerHTML += new_log_lines;
            // scroll to bottom
            target_div.scrollTop = target_div.scrollHeight;
            // FIFO the message, keeping an arbitrary 200
            // Otherwise we could have 10's of thousands.  Not cool.
            var count = target_div.childElementCount;
            while (count > 200) {
                target_div.removeChild(target_div.firstChild);
                count--;
            }
        }
    }

    // Add a span that includes 3 buttons,right justified.  In that,
    // three small badges. aSee if there's a text-small class
    // Badge.  Want to add these to each stderr window with count
    //         of error warning/error/criticals.
    // <span class="position-absolute top-0 start-100
    //              translate-middle badge rounded-pill bg-danger">
    // Add the d-none class, toggle that when count > 0             
    // 99+
    // </span>
    var crit = {};
    var errs = {};
    var warn = {};
    function color_log_line (message, target) {
        var color = 'text-body';
        if (message.includes (' 30 WARNING ') > 0) {
            color = 'text-warning';
            warn[target] = warn[target] + 1 || 1;
        }
        else if (message.includes (' 40 ERROR ') > 0) {
            color = 'text-warning bg-dark';
            errs[target] = errs[target] + 1 || 1;
        }
        else if (message.includes (' 50 CRITICAL ') > 0) {
            color = 'text-light bg-danger';
            crit[target] = crit[target] + 1 || 1;
        }
        message = '<span class="' + color + '">' + message + '</span><br />';
        return message;
    }

    /////////////////////////////////////////////////////////////////
    //
    // Code for handling the context menu on the STDERR windows
    //
    /////////////////////////////////////////////////////////////////
    var currentContextTarget = null;
    var ctxmenu = function(evt) {
        evt.preventDefault();
        ctx_menu_html.style.left = evt.pageX + 'px';
        ctx_menu_html.style.top = evt.pageY + 'px';
        ctx_menu_html.classList.add('menu-show');
        // debug code
        var div = evt.currentTarget;
        currentContextTarget = div;
        if (div.id.endsWith('_stderr')) {
            id = div.id.slice(0, -7);
            // console.info('Show context menu for', id);
            
        } else {
            // console.warn('Context menu on inappropriate div', id);
        }
    }

    var ctx_ack = function(evt) {
        // console.log("ctx_ack called:");
        // console.log("currentContextTarget =", currentContextTarget.id);
        ctx_menu_html.classList.remove('menu-show');
    }

    var ctx_clear = function(evt) {
        // console.log("ctx_clear called:");
        // console.log("currentContextTarget =", currentContextTarget.id);
        var d = currentContextTarget;
        while (d.lastElementChild) {
            d.removeChild(d.lastElementChild);
        }
        ctx_menu_html.classList.remove('menu-show');
    }

    var create_ctx_menu_html = function() {
        //<ul class="menu" id="context-menu">
        var ul = document.createElement('ul');
        ul.className = 'menu';
        ul.setAttribute('id', 'STDERR-context-menu');
        //<li class="menu-item">
        var li = document.createElement('menu');
        li.className = 'menu-item';
        // <a href="#" onClick="STDERR.ctx_ack()" class="menu-btn">
        var a = document.createElement('a');
        a.className = 'menu-btn';
        a.addEventListener('click', ctx_ack);
        // <span class="menu-text">Acknowlege</span>
        var sp = document.createElement('span');
        sp.className = 'menu-text';
        sp.innerHTML = 'Acknowlege';
        a.appendChild(sp);
        // </a>
        li.appendChild(a);
        // </li>
        ul.appendChild(li);
        // <li class="menu-item">
        li = document.createElement('li');
        li.className = 'menu-item';
        // <a href="#" onClick="STDERR.ctx_clear()" class="menu-btn">
        var a = document.createElement('a');
        a.className = 'menu-btn';
        a.addEventListener('click', ctx_clear);
        // <span class="menu-text">Clear</span>
        var sp = document.createElement('span');
        sp.className = 'menu-text';
        sp.innerHTML = 'Clear';
        a.appendChild(sp);
        // </li>
        li.appendChild(a);
        // </ul>
        ul.appendChild(li);
        return ul;
    }

    // only run once when function instantiates
    var ctx_menu_html = create_ctx_menu_html();
    document.body.appendChild(ctx_menu_html);

    // FIXME:  Figure out how to refactor stuff so we do not
    //         need to export the context menu functions.
    return {
        process: process,
        ctxmenu: ctxmenu,
    }

})();

