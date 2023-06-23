//
//    @/modals.js
//
//    contains the HTML for the modal dialogues for
//    changing logger_manager mode or individual logger
//    modes.
//
//    Modals are the new popup.  Popups are the old
//    dead to me.
//
//    Basic premise here is that the modals get filled in
//    by an fetch to a CGI (written in python), and
//    submit changes via POST to the same script.
//
//    Associated javascript file(s) is/are planned, but for the 
//    moment the associated code is here inside a <script> tag.


var CGI = (function() {
    var AjaxGet = async function(url) {
        try {
            response = Ajax('GET', url);
        } catch (error) {
            return { ok: false, error: error };
        }
        return response;
    };

    var AjaxPost = async function(evt, form, parentModal) {
        // Don't do typical "submit" action, do this instead
        evt.preventDefault();
        jwt = localStorage.getItem('jwt_token');
        post_options = {
            method: 'post',
              body: new FormData(form),
           headers: { 'Authorization': 'Bearer ' + jwt }
        };
        url = form.action;
        var post = await fetch(form.action, post_options);
        if (!post.ok) {
            // console.error("Post of form not OK");
            var t = await post.text();
            iziToast.error({
                title: 'Error',
                message: t,
            });
            return false;
        } else {
            // POST is OK, so mode was (probably) changed.
            var el = document.getElementById(parentModal);
            var our_modal = bootstrap.Modal.getInstance(el);
            if (our_modal) {
                our_modal.hide();
            } else {
                console.error("our_model isn't our modal :-(");
            }
        }
        return false;
    };

    return {
        AjaxGet: AjaxGet,
        AjaxPost: AjaxPost,
    };

})();

var LoggerModal = (function() {
    var modal_el = document.getElementById("LoggerModal");
    var title_el = document.getElementById("LoggerModalTitle");
    var body_el  = document.getElementById("LoggerModeModalBody");
    var bsm = bootstrap.Modal.getOrCreateInstance(modal_el);
    var timer = null;

    function kill_timeout() {
        clearTimeout(timer);
    }

    async function show(evt) {
        function auto_close() {
            if (bsm) {
                bsm.hide();
            }
        }
        bsm.show();
        // fill in the modal title
        var el = evt.target;
        var logger_id = el.attributes.for.value;
        if (title_el) {
            title_el.innerHTML = "Change " + logger_id + " mode";
        }
        // fill in modal body
        var url = '/cgi-bin/LoggerMode.cgi?' + logger_id;
        var result = await CGI.AjaxGet(url);
        timer = setTimeout(auto_close, 30000);
        if (body_el) {
            body_el.innerHTML = result;
        }
    }

    var init = function() {
        if (modal_el) {
            modal_el.addEventListener('hide.bs.modal', kill_timeout);
        } else {
            console.warn("No Cruise Mode modal dialogue found !!");
        }
    };

    init();

    return {
        show: show,
    }

})();


var LoggerButton = (function() { 

    function create(logger_id, text) {
        var b = document.createElement('button');
        b.setAttribute('id', logger_id + "_btn");
        b.setAttribute('type', 'button');
        b.setAttribute('for', logger_id);
        b.setAttribute('onclick', 'LoggerModal.show(event);');
        b.className = 'btn btn-secondary btn-sm';
        b.innerHTML = text;
        return b;
    }

    // This function should be called by index.html to update
    // the button's innerHTML and style (on status change)
    var status_timestamp = 0;

    function update(timestamp, logger_status) {
        // Don't update buttons if this message is old.
        if (timestamp <= status_timestamp) {
            console.debug('Got stale logger status - skipping...');
            return false;
        }
        status_timestamp = timestamp;

        // Bail if logger_status is empty
        if (!logger_status || Object.keys(logger_status).length == 0) {
            return;
        }

        // For each logger, set button style
        for (var logger_name in logger_status) {
            var status = logger_status[logger_name];
            var button = document.getElementById(logger_name + '_btn');
            if (!button) {
                continue;
            }
            button.innerHTML = status.config;
            var extra_class = "";
            var button_color = "";
            switch (status.status) {
                case 'RUNNING':
                    extra_class = 'btn-success';
                    break;
                case 'EXITED':
                    extra_class = 'btn-secondary';
                    break;
                case 'STARTING':
                    button_color = 'khaki';
                    break;
                case 'BACKOFF':
                    button_color = 'gold';
                    break;
                case 'FATAL':
                    extra_class = 'btn-danger';
                    break;
                default:
                    break;
            } // esac 
            button.className = 'btn btn-sm ' + extra_class;
            button.style.backgroundColor = button_color;
        }
    }

    function mode_update(logger_id, mode) {
        var el_name = logger_id + '_btn';
        var el = document.getElementById(el_name);
        if (el) {
            el.innerHTML = mode;
        }
        if (odas.api.loggers[logger_id].active != mode) {
            console.warn('API mode differs from passed mode');
        }
    } 
        

    // methods for LoggerButton
    return {
        // shown: shown,
        // show: show,
        create: create,
        update: update,
        mode_update: mode_update,
    };
})();


/////////////////////////////////////////////////////////////////
//
//  CruiseModeModal
//
//  Manage the events needed to operate the cruise mode button
//
/////////////////////////////////////////////////////////////////
// NOTE:  Why is this so much simpler than the logger button?
//        I really should have coded them at the same time...
var CruiseModeModal = (function() {

    var button = document.getElementById("mode_button");
    var modal = document.getElementById("CruiseModeModal");
    var modal_body = document.getElementById("CruiseModeModalBody");
    var timer = null;

    function kill_timeout() {
        clearTimeout(timer);
    }

    async function show_modal(evt) {
        function auto_close() {
            var bsm = bootstrap.Modal.getOrCreateInstance(modal);
            if (bsm) {
                bsm.hide();
            }
        }
        var result = await CGI.AjaxGet("/cgi-bin/CruiseMode.cgi");
        timer = setTimeout(auto_close, 30000);
        if (modal_body) {
            modal_body.innerHTML = result;
        }
    }

    var init = function() {
        if (button) {
            button.addEventListener('click', show_modal);
        } else {
            console.warn("No cruise mode button found !!");
        }
        if (modal) {   
            modal.addEventListener('hide.bs.modal', kill_timeout);
        } else {
            console.warn("No Cruise Mode modal dialogue found !!");
        }
    };

    init();

})();

var Reload_Button = (function() {
    // Called by the 'clicked' mehtod
    var reload_el = document.getElementById('reload_config_link');
 
    async function shown() {
        function auto_close() {
            var el = document.getElementById('LoadButton_Modal');
            var modal = bootstrap.Modal.getOrCreateInstance(el);
            if (modal) {
                modal.hide();
            }
        }
        var fname = reload_el.title;
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
 
    var clicked = function(evt) {
        if (typeof autoClose === 'object') { 
            autoClose.reset();
        }
        var el = document.getElementById('LoadButton_Modal');
        if (el) {
            el.addEventListener('show.bs.modal', shown());
        }
        var our_modal = bootstrap.Modal.getOrCreateInstance(el);
        if (our_modal) {
            our_modal.show();
        }
    }

    function init() {
        if (reload_el) {
            reload_el.setAttribute('onclick', 'Reload_Button.clicked()');
        }
    }
    init();

    return {
        clicked: clicked,
    };

})();

