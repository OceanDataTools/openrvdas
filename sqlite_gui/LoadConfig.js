//
// sqlite_gui/LoadConfig.js
//
// Javascript for the page that browses and loads config files
//
//

var current_directory = "";
var current_file = "";
var yaml_editor = null;

// FIXME:  Set a timeout timer.  If we don't click a dir/file/load button
//         for 10 minutes, close this page.
//
////////////////////////////////////////////////////////////////////////////
//
// Function to handle messages from the CDS.  We only need a small subset
// of the normal handling for this page.
//
////////////////////////////////////////////////////////////////////////////
var cruise_def = (function() {
    var saved_timestamp = 0;
    var saved_filename = "";

    function update(payload) {
        // Get the data from the last message in the list
        [ timestamp, last] = payload.pop();
        if (timestamp <= saved_timestamp) {
            return;
        }
        saved_timestamp = timestamp;
        odas.api = last;
        // console.info(JSON.stringify(last, null, "  "));
        console.info("Filename = " + last.filename);
        if (last.filename != saved_filename) {
            console.info("Filename has changed: " + last.filename);
            saved_filename = last.filename;
            var el = document.getElementById('current_file');
            el.setAttribute('placeholder', last.filename);
            el = document.getElementById('cruise_id');
            if (el) {
                var txtNode = el.childNodes[0];
                txtNode.nodeValue = odas.api.cruise_id || ' CruiseID ';
            }
            // FIXME: load into the editor
            load_file(current_directory, last.filename);
        }
    }

    return {
        update: update,
    };
})();

var file_update = (function() {
    function update(payload) {
        var timestamp, file_time, staleSpan;

        // Get the data from the last message in the list
        [ timestamp, file_time ] = payload.pop();
        if (file_time <= odas.api.config_timestamp) {
            return;
        }
        staleSpan = document.getElementById('stale_span');
        if (staleSpan) {
            staleSpan.classList.remove('d-none');
        }
    }

    return {
        update: update,
    };
})();

function extra_parser(message) {
    var j = {};
    try {
        j = JSON.parse(message);
    } catch (err) {}
    if ((j.status != 200) || (j.type != 'data')) {
        return;
    }
    
    var payload = j.data;
    for (var msg in payload) {
        if (msg == 'status:cruise_definition')
            cruise_def.update(payload[msg]);
        if (msg == 'status:file_update')
            file_update.update(payload[msg]);
     }
}

// The default CDS parser defined in index.html.js won't get activated, but
// we need to have some sort of parser to handle a couple things on 
// the menubar.  This is it.
WS.add_parser(extra_parser);

// end of code for handling CDS messages
////////////////////////////////////////////////////////////////////////

// 5 minute timeout
// If nobody clicks a significant button, then close this window
// Significant buttons are a file/dir in the left column
var autoClose = (function() {
    var timer;
    function close_me() {
        window.close();
    }
    function reset() {
        clearTimeout(timer);
        timer = window.setTimeout(close_me, 5 * 60 * 1000);
    }
    reset()
    return {
        reset: reset,
    }
})();

async function load_file(dir, fname) {
    var FileList;
    try {
        var QS = 'dir=' + dir + '&file=' + fname;
        FileList = await Ajax('get', 'cgi-bin/FileBrowser.cgi?' + QS);
    } catch(err) {
        console.error(err);
    }
    if (yaml_editor) {
        yaml_editor.setValue(FileList.text);
    }
}

async function yproxy() {
    var url = '/cgi-bin/YamlLint.cgi?fname='
    var el = document.getElementById('current_file');
    var fname = el.value || el.placeholder;
    if (fname == "name of current config file") {
        return {};
    }
    url = url + fname;
    var our_line = {};
    try {
        our_lint = await Ajax('get', url);
    } catch (e) {};
    return our_lint;
}

window.yproxy = yproxy;

async function dir_clicked(evt) {
    autoClose.reset();
    var target = evt.target;
    var name = target.innerText;
    console.log("Clicked " + name);
    if (name == "..") {
        var c = current_directory;
        var d = c.substring(0, c.lastIndexOf('/'));
        current_directory = d;
    } else {
        current_directory = current_directory + '/' + name;
    }
    // FIXME:  
    // Bad... we're just going to get this HUGE call stack
    // Need to refactor our calling logic.
    // On the other hand, how long do we stay on this page?
    // FIXME:  Enforce that.  If no clicks in 10 minutes, close,
    var FileList = await ListFiles(current_directory);
    Load_Files(FileList);
}

// Loads the clicked file into the editor window so the
// yaml lint can look at it.
// FIXME:  The yaml linter wth CodeMirror is... sub-optimal
//         See: https://codepen.io/facka/pen/ExPrMRd
//         Same linter, but code looks a lot lighter.
function file_clicked(evt) {
    autoClose.reset();
    var target = evt.target;
    var name = target.innerText;
    console.log("File Clicked " + name);
    var current_file = name;
    var el = document.getElementById('current_file');
    el.setAttribute('placeholder', current_directory + '/' + name);
    load_file(current_directory, name);
    return false;
}

// Utility function to add a new element to the DOM
function addElement(parent_el, type, cls, contents) {
    var el = document.createElement(type);
    if (cls) {
        el.className = cls;
    }
    if (contents) {
        el.innerHTML = contents;
    }
    parent_el.appendChild(el);
    return el;
}

// utility function to add a 'br' element to the DOM
function addBreak(parent_el) {
    var el = document.createElement('br');
    parent_el.appendChild(el);
}


function Load_Files(FileList) {
    // display 'root' of our filebrowser
    fb = document.getElementById('file_list');
    // Fast and dirty clear an element's children
    // faster to use replaceChildren(), but may be support issues
    while (fb.firstChild) { fb.removeChild(fb.lastChild); }
    // Show current directory
    addElement(fb, 'i', '', FileList.dir);
    addBreak(fb);
    // Show "up" ".." thingee
    s = addElement(fb, 'i', 'bi-arrow-90deg-up', '');
    s = addElement(fb, 'a', '', "  ..");
    addBreak(fb);
    s.addEventListener('click', dir_clicked);
     
    // Add the dirs and files.  
    for (var dir in FileList.dirs) {
        addElement(fb, 'i', 'bi-folder', '');
        var a = addElement(fb, 'a', '', "  " + FileList.dirs[dir]);
        a.addEventListener('click', dir_clicked);
        addBreak(fb);
    }
    for (var file in FileList.files) {
        var b = addElement(fb, 'a', '', FileList.files[file]);
        b.addEventListener('click', file_clicked);
        addBreak(fb);
    }
}

// Get the list of files and dirs
async function ListFiles(dir) {
    var FileList = {};
    try {
        FileList = await Ajax('get', 'cgi-bin/FileBrowser.cgi?dir=' + dir);
    } catch(err) {
        console.error(err);
    }
    return FileList;
}

// Maybe we need a better name than "do_stuff"
async function do_stuff() {
    // Initialize the editor window
    var el = document.getElementById('editor');
    yaml_editor = CodeMirror.fromTextArea(el, {
        value: "Test Text",
        lineNumbers: true,
        mode: 'yaml',
        gutters: ['CodeMirror-lint-markers'],
        lint: true,
        scrollbarStyle: "simple",
        readOnly: true,
    });
    // FIXME:  Set vertical size based on window size.
    yaml_editor.setSize('100%', '18em');

    // Load config
    await Load_Config();

    var dir = odas.confdir || '/opt/openrvdas/local';
    current_directory = dir;
        
    var FileList = await ListFiles(dir);
    Load_Files(FileList);
}

//////////////////////////////////////////////////////////////////////////
//
//  Load Button   # FIXME:  Need something for reload, too
//
//////////////////////////////////////////////////////////////////////////
var LoadButton = (function() {
    // Called by the 'clicked' mehtod
    async function shown() {
        function auto_close() {
            var el = document.getElementById('LoadButton_Modal');
            var modal = bootstrap.Modal.getOrCreateInstance(el);
            if (modal) {
                modal.hide();
            }
        }
        var el = document.getElementById('current_file');
        var fname = el.value || el.placeholder;
        // FIXME:  Should not load via GET
        var params = 'verb=load&fname=' + fname;
        var url = 'cgi-bin/FileBrowser.cgi?' + params;
        // FIXME:  Can I use Ajax here?
        var result = await CGI.AjaxGet(url);
        // Response received, set up auto-close
        setTimeout(auto_close, 30000); // 30 seconds is an eternity
        // Should have token, etc
        var dest = document.getElementById('LoadButton_mb');
        if (dest) {
            dest.innerHTML = result.html;
        }
    }

    function clicked(evt) {
        autoClose.reset();
        var el = document.getElementById('LoadButton_Modal');
        if (el) {
            el.addEventListener('show.bs.modal', shown());
        }
        var our_modal = bootstrap.Modal.getOrCreateInstance(el);
        if (our_modal) {
            our_modal.show();
        }
    }

    return {
        clicked: clicked,
    };
    
})();


