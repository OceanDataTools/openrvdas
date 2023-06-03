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
var global_loggers = {};
var global_active_mode = 'off';
var global_last_cruise_timestamp = 0;
var global_last_cruise_mode_timestamp = 0;
var global_last_logger_status_timestamp = 0;

var odas = new Object;
//odas.loggers = {};
//odas.active_mode = 'off';
//odas.last_cruise_timestamp = 0;
//odas.last_cruise_mode_timestamp = 0;
//odas.last_logger_status_timestamp = 0;


// Caveat Emptor:  Errors are thrown
async function Ajax(method, url, options = {}) {
    var fetch_options = {};
    if (method.toLowerCase() == 'post') {
        jwt = localStorage.getItem('jwt_token');
        var auth_header = {'Authorization': 'Bearer ' + jwt}
        fetch_options['method'] = 'post';
        fetch_options['body'] = options.body;
        fetch_options['headers'] = auth_header;
    }
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

//
//  LoginButton 
//
//  Purpose:
//      Manage "Log In" button and cache auth information.
//
//  On page load checks for expired auth.  We won't check again until
//  next page load, but the CGI's may (or may not) worry about expired
//  auth, and even (roadmap) provide updated auth tokens.
//  FIXME:  Look into WebAuthn (fingerprint, etc)
//  
var LoginButton = (function() {

    var button = document.getElementById('login_button');

    // on_load() ==> (nothing)
    //
    // Called by body_load() to decorate the Login button 
    // Auth is in the form a a JSON Web Token.  See https://jwt.io 
    var on_load = function() {
        var jwt = localStorage.getItem('jwt_token');
        if (jwt) {
            try {
                username = check_jwt(jwt);
                logged_in(username);
            } catch (error) {
                console.warn(error);
                logged_out();
            }
        } else {
            logged_out();
        }
    }

    // We only use a couple fields in our JWT payload 
    // exp: expiration time after which token is invalid
    //      for us, that's 90 days after you log in.
    // iat: issued at time
    // name: username.
    var check_jwt = function(jwt) {
        // only one part of the JWT is not encyrpted.  Get it.
        var s = jwt.split('.');
        if (s.length < 2) {
            throw new Error("JWT lacking dots: " + jwt);
        }
        // We appear to have a payload.  Try it.
        var dec = atob(s[1]);
        try {
            var payload_obj = JSON.parse(dec);
        } catch(error) {
            throw new Error("JWT payload indeciferable: " + dec);
        }
        // Check for expired token
        if (!payload_obj.exp) { 
            throw new Error("No expiration time in JWT.  Assuming invalid");
        }
        var exp = new Date(payload_obj.exp * 1000);
        if (exp < Date.now()) {
            throw new Error("JWT auth token expired.  Need to log in.");
        }
        // Check for a name in the payload
        if (!payload_obj.name) {
            throw new Error("No name in JWT auth token.  Assuming invalid");
        }
        return payload_obj.name;
    }

    // No JWT or JWT invalid (so not logged in)
    var logged_out = function() {
        if (button) {
            button.innerHTML = 'Log In';
        }
        var el = document.getElementById('login_action');
        if (el) {
            el.setAttribute('value', 'login');
        }
        localStorage.removeItem('jwt_token');
        el = document.getElementById('login_submit_button');
        if (el) {
            el.innerHTML = 'Log In';
        }
    }

    // The submit button was pressed (to log in, or log otu)
    var pressed = async function(evt, form) {
        // Keep it from navigating to the action url.
        evt.preventDefault();
        var el = document.getElementById('login_action');
	action = el.getAttribute('value');
        if (action == 'logout') {
            logged_out();
            return false;
        }
        options = {
            body: new FormData(form)
        }
        try {
            response = await Ajax('post', form.action, options);
        } catch (error) {
            console.error(error);
            return false;
        }
        try {
            obj = JSON5.parse(response);
        } catch (error) {
            console.error(response, error);
            return false;
        }
        if (obj.jwt) {
            try {
                username = check_jwt(obj.jwt);
                localStorage.setItem('jwt_token', obj.jwt);
                logged_in(username);
            } catch (error) {
                logged_out();
                // FIXME: something cooler than 'alert'
                alert(error);
            }
        }
    }

    var logged_in = function(name) {
        var el = document.getElementById('login_action');
	if (el) {
	    el.setAttribute('value', 'logout');
	}
        if (button) {
            button.innerHTML = name;
        }
        el = document.getElementById('login_submit_button');
        if (el) {
            el.innerHTML = 'Log Out';
        }
    }

    return {
        on_load: on_load,
        pressed: pressed
    }

})();

////////////////////////////////////////////////////////////////////////////
//
//  Theme
//
//      Class to handle the themes.
//      Exports two functions:
//      - on_load - Loads the initial theme (if any)
//      - change  - Tries to change the theme to supplied option
//
var Theme = (function() {

    var css_el = document.getElementById('theme-css');

    var on_load = function() {
        theme = localStorage.getItem('theme');
        if (theme) {
            change(theme);
        }
    }

    var change = function(theme) {
        if (!css_el) { return; }
        var url = '/js/themes/' + theme + '/bootstrap.min.css';
        url += '?' + Date.now();
        css_el.setAttribute('href', url);
        localStorage.setItem('theme', theme);
    }

    return {
        on_load: on_load,
        change: change
    }

})();

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
        var o = await Ajax('GET', '/openrvdas.json5')
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
    Theme.on_load();
    // Login Button
    LoginButton.on_load();
}
