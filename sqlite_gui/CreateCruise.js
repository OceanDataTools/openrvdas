//
// sqlite_gui/LoadConfig.js
//
// Javascript for the page that browses and loads config files
//
//

var current_directory = "";
var current_file = ""
var yaml_editor = null;

// FIXME:  Set a timeout timer.  If we don't click a dir/file/load button
//         for 10 minutes, close this page.
//
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
        // console.info(JSON.stringify(last, null, "  "));
        console.info("Filename = " + last.filename);
        if (last.filename != saved_filename) {
            console.info("Filename has changed: " + last.filename);
            saved_filename = last.filename;
            var el = document.getElementById('current_file');
            el.setAttribute('placeholder', last.filename);
            // FIXME: load into the editor
            load_file(current_directory, last.filename);
        }
    }

    return {
        update: update,
    }
})();

async function load_file(dir, fname) {
    try {
        QS = 'dir=' + dir + '&file=' + fname;
        var FileList = await Ajax('get', 'cgi-bin/FileBrowser.cgi?' + QS);
    } catch(err) {
        console.error(err);
    }
    if (yaml_editor) {
        yaml_editor.setValue(FileList.text);
    }
}

var file_update = (function() {
    var saved_file_time = 0;

    function update(payload) {
        // Get the data from the last message in the list
        [ timestamp, file_time ] = payload.pop();
        if (file_time <= saved_file_time) {
            return;
        }
        saved_file_time = file_time;
        console.info(JSON.stringify(file_time, null, "  "));
        // FIXME: If we get here, config is stale.  Badge, etc.
    }

    return {
        update: update,
    }
})();


function extra_parser(message) {
    j = {};
    try {
        j = JSON.parse(message);
    } catch {};
    if ((j.status != 200) || (j.type != 'data')) {
        return;
    }
    
    payload = j.data;
    for (msg in payload) {
        if (msg == 'status:cruise_definition')
            cruise_def.update(payload[msg]);
        if (msg == 'status:file_update')
            file_update.update(payload[msg]);
     }
}

async function dir_clicked(evt) {
    target = evt.target;
    name = target.innerText;
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
    FileList = await ListFiles(current_directory);
    Load_Files(FileList);
}

function file_clicked(evt) {
    target = evt.target;
    name = target.innerText;
    console.log("File Clicked " + name);
    current_file = name;
    var el = document.getElementById('current_file');
    el.setAttribute('placeholder', current_directory + '/' + name);
    load_file(current_directory, name);
    return false;
}


// FIXME:  CSS the links hover color
function Load_Files(FileList) {
    // display 'root' of our filebrowser
    fb = document.getElementById('file_list');
    // Fast and dirty clear an element's children
    if (typeof fb.replaceChildren === 'function' ) {
        fb.replaceChildren();
    } else {
        while (fb.firstChild) { fb.removeChild(fb.lastChild); }
    }
    // Show current directory
    s = document.createElement('i');
    s.innerHTML = FileList.dir;
    fb.appendChild(s);
    br = document.createElement('br');
    fb.appendChild(br);
    // Show "up" ".." thingee
    i = document.createElement('i');
    i.className = "bi-arrow-90deg-up";
    fb.appendChild(i);
    dname = "..";
    a = document.createElement('a');
    a.innerHTML = dname;
    fb.appendChild(a);
    br = document.createElement('br');
    fb.appendChild(br);
    a.addEventListener('click', dir_clicked);
     
    // Empty out the element
    for (dir in FileList.dirs) {
        i = document.createElement('i');
        i.className = "bi-folder";
        fb.appendChild(i);
        dname = FileList.dirs[dir];
        a = document.createElement('a');
        a.innerHTML = dname;
        fb.appendChild(a);
        br = document.createElement('br');
        fb.appendChild(br);
        a.addEventListener('click', dir_clicked);
    }
    for (file in FileList.files) {
        fname = FileList.files[file];
        a = document.createElement('a');
        a.innerHTML = fname;
        fb.appendChild(a);
        br = document.createElement('br');
        fb.appendChild(br);
        a.addEventListener('click', file_clicked);
    }
}

async function ListFiles(dir) {
    try {
        var FileList = await Ajax('get', 'cgi-bin/FileBrowser.cgi?dir=' + dir);
    } catch(err) {
        console.error(err);
    }
    return FileList;
}

// We don't need (or want) the regular parsers for the websocket
// data.  We only need a small subset here.
ws.add_parser(extra_parser);


async function do_stuff() {
    // Initialize the editor window
    var el = document.getElementById('editor');
    yaml_editor = CodeMirror.fromTextArea(el, {
        value: "Test Text",
        lineNumbers: true,
        mode: 'yaml',
        gutters: ['CodeMirror-lint-markers'],
        lint: true,
        scrollbarStyle: "simple"
    });
    // FIXME:  Set size based on window size.
    yaml_editor.setSize('100%', '18em');

    // Load config
    await Load_Config_JSON();
    // Load Theme
    Theme.on_load();
    // Init Login Button
    LoginButton.on_load();

    if (odas) { 
        dir = odas.confdir || '/opt/openrvdas/local';
    }
    current_directory = dir;
        
    var FileList = await ListFiles(dir);
    Load_Files(FileList);
}





