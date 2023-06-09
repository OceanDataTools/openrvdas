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

var odas = new Object;


// Caveat Emptor:  Errors are thrown
async function Ajax(method, url, options = {}) {
    var fetch_options = options || {};
    if (method.toLowerCase() == 'post') {
        jwt = localStorage.getItem('jwt_token');
        var auth_header = {'Authorization': 'Bearer ' + jwt}
        fetch_options['method'] = 'post';
        fetch_options['body'] = options.body;
        fetch_options['headers'] = auth_header;
    }
    // FIXME:  Add a timeout (AbortController)
    //         Wrap fetch in try/catch (in case server is down)
    const response = await fetch(url, fetch_options);
    if (!response.ok) {
        e = { error: response.status,
              reason: response.statusText,
              response: response
            };
        console.error('fetch error: ', JSON.stringify(e, null, "  "))
        // var errobj = {};
        // errobj.message = response.statusText;
        // errobj.name = response.status + " error"
        // throw (errobj)
        // new Error(message, cause) 
        throw new Error(e);
    }
    var j = await response.text();

    // convert weird response.headers object to normal object
    var headers = {}
    for (var pair of response.headers.entries()) {
        headers[pair[0]] = pair[1];
    }
        
    // If we received JSON, parse it.
    if (headers['content-type'] == 'application/json') {
        try {
            var j5 = JSON5.parse(j);
        } catch (error) {
            console.error('JSON5 error: ', j, error);
            e = { error: true,
                  body: j,
                  reason: error
                };
            throw new Error(e);
        } finally {
            j = j5;
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
//      global values.
//
async function Load_Config_JSON() {
    // Fix up "Links", replacing "${host}" with hostname
    function fix_up_links(o) {
        for (var key in o.Links) {
            var l = o.Links[key];
            if (o.Links[key].url) {
                var s = o.Links[key].url;
                s = s.replace('${host}', document.location.host);
                o.Links[key].url = s
            }
        }
        return o;
    }

    // Add to "Links" dropdown on navbar
    function addLinks(links) {
        for (var key in links) {
            var link = links[key];
            var aLli = document.createElement('li');
            var aLa = document.createElement('a');
            aLa.className = 'dropdown-item';
            aLa.setAttribute('href', link.url);
            aLa.setAttribute('target', '_new');
            if (!link.name) {
                link.name = key;
            }
            aLa.innerHTML = link.name;
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
                console.error(error);
            }
        }
    }

    // Called when openrvdas.json5 has been loaded
    function jsonLoaded(o) {
        // If we have "Links", replace ${host} 
        if (o.Links) {
            o = fix_up_links(o);
            addLinks(o.Links);
        }
        if (!window.odas) {
            window.odas = new Object;
        }
        window.odas = new Object; // create global object 
        for (var key in o) {
            odas[key] = o[key];
        }
    }

    try {
        var o = await Ajax('GET', '/openrvdas.json')
        jsonLoaded(o);
    } catch (error) {
        console.error(error);
    }
}
////////////////////////////////////////////////////////////////////////////
//
//  body_laod() ==> (nothing)
//
//      Called when the body of the page has been loaded.  Handles
//      basic initialization tasks:
//      - Setting up the login button on the navbar
//      = Loading the config file
//      - Setting the theme
//
async function body_load() {
    // Load the config JSON (json5, actually)
    await Load_Config_JSON();
    // Load theme (if any)/
    // Theme.on_load();
    // Login Button
    // LoginButton.on_load();
}
