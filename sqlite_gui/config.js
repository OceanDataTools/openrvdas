//////////////////////////////////////////////////////////////////////////////
// Javascript for the 'head.html' stub included in all (most) of
// the webpages presented to the public.
//
// includes fixups for the navbar, login/logout forms, and gets us 
// our (former) framework variables
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


// Why are these separate globals?  The timestamps, in
// particular should probably be captured by the objects that
// handle these updates.  Oh yeah, one other thing, make the
// functions that handle these updates be methods of objects.  :-)

var odas = {};


// Caveat Emptor:  Errors are thrown
async function Ajax(method, url, options={}) {
    var fetch_options = options || {};
    if (method.toLowerCase() == 'post') {
        jwt = localStorage.getItem('jwt_token');
        var auth_header = {'Authorization': 'Bearer ' + jwt};
        fetch_options.method = 'post';
        fetch_options.body = options.body;
        fetch_options.headers = auth_header;
    }
    // NOTE:  Add a timeout (AbortController)
    // NOTE:  I tried wrapping fetch in try/catch (in case server
    //        is down), but got a promise instead of a response
    const response = await fetch(url, fetch_options);
    if (!response.ok) {
        // this means the rquest completes poorly.
        e = {
            title: 'fetch error',
            message: response.statusText || 'Unknown error',
        };
        iziToast.error(e);
        throw new Error(e);
    }
    var j = await response.text();

    // convert weird response.headers object to normal object
    var headers = {};
    for (var pair of response.headers.entries()) {
        headers[pair[0]] = pair[1];
    }
        
    // If we received JSON, parse it.
    if (headers['content-type'] == 'application/json') {
        try {
            var j5 = JSON5.parse(j);
            j = j5;
        } catch (error) {
            iziToast.error({
                title: 'JSON5 error',
                message: error,
            });
            throw error;
        }
    }
    return j;
}

////////////////////////////////////////////////////////////////////////////
//
//  Load_Config_JSON() ==> (nothing)
//
//      Loads the file openrvdas.json5 (found in this directory)
//      Creates and populates the 'odas' object which holds the
//      global config values.
//
function Load_Config() {

    // Add to "Links" dropdown on navbar
    function addLinks(links) {
        for (var key in links) {
            var link = links[key];
            var aLli = document.createElement('li');
            var aLa = document.createElement('a');
            aLa.className = 'dropdown-item';
            aLa.setAttribute('href', link.url);
            aLa.setAttribute('target', '_new');
            aLa.innerHTML = link.name || key;
            // What about tooltips?
            if (link.tooltip) {
                aLa.setAttribute('data-bs-toggle', 'tooltip');
                aLa.setAttribute('data-bs-placement', 'top');
                aLa.setAttribute('title', link.tooltip);
            }
            aLli.appendChild(aLa);
            try {
                var el = document.getElementById('links_dropdown');
                el.appendChild(aLli);
            } catch (error) {
                iziToast.warning({
                    title: 'Unable to add link',
                    message: error,
                });
                // console.error(error);
            }
        }
    }

    // Have to load the config synchronous, not async
    // otherwise our config values will not exists by 
    // the time the other script files need them.
    // 
    var r = new XMLHttpRequest();
    r.open('GET', '/openrvdas.json', false);
    r.send(null);
    if (r.status == 200) {
        window.odas = {}; // explicitly create global object
        try {
            odas = JSON5.parse(r.responseText);
            if (odas.Links) {
                for (var key in odas.Links) {
                    var link = odas.Links[key];
                    if (link.url) {
                        var s = link.url;
                        s = s.replace('${host}', document.location.host);
                        odas.Links[key].url = s;
                    }
                 }
                 // fix_up_links(odas);
                 addLinks(odas.Links);
            }
        } catch (e) {
            iziToast.error({
                title: 'Error in config file',
                message: e,
            });
        }
    } else {
        cosole.error("Unable to load config file");
    }
}

Load_Config();
