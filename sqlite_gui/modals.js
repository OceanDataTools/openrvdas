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


var LoggerButton = (function() { 
    // Event handler called when the modal is shown on the page.
    // The modal is shown on the page when you click a logger button
    //
    // shown(element_id)  ==> nothing
    //     @element_id = DOM element id of the button
    var shown = async function(element_id) {
        // auto_close after timeout
        function auto_close() {
            var el = document.getElementById('LoggerModal');
            var modal = bootstrap.Modal.getOrCreateInstance(el);
            if (modal) {
                modal.hide();
            }
        }
        // Set modal title
        var logger_id = element_id.attributes.for.value;
        var title_el = document.getElementById('LoggerModalTitle');
        if (title_el) {
            title_el.innerHTML = "Change " + logger_id + " mode";
        }
        // fill in modal body
        url = '/cgi-bin/LoggerMode.cgi?' + logger_id;
        var result = await CGI.AjaxGet(url);
        setTimeout(auto_close, 30000);
        var dest = document.getElementById('LoggerModeModalBody');
        if (dest) {
            dest.innerHTML = result;
        } 
    };

    // Event handler called when the button is clicked
    //   Get the modal, attach listener, and show it.
    //   We should not anonymous inline the 'shown' method, See
    // https://developer.mozilla.org/en-US/docs/Web/API/EventTarget/addEventListener
    //
    // show(element_id)  ==> nothing
    //     @element_id - DOM element id of the button 
    function show(element_id) {
        var el = document.getElementById('LoggerModal');
        if (el) {
            el.addEventListener('show.bs.modal', 
                                LoggerButton.shown(element_id));
        }
        var our_modal = bootstrap.Modal.getOrCreateInstance(el);
        if (our_modal) {
            our_modal.show();
        }
    }

    // creates a logger button to display on the GUI
    //
    // create(logger_id, text) ==> button element
    //    @logger_id - ServerAPI logger id for this button
    //    @text      - initial text shown on the button face
    function create(logger_id, text) {
        var b = document.createElement('button');
        b.setAttribute('id', logger_id + "_btn");
        b.setAttribute('type', 'button');
        b.setAttribute('for', logger_id);
        b.setAttribute('onclick', 'LoggerButton.show(this)');
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

        // Update timestamp on status_td
        status_td.update();

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
        shown: shown,
        show: show,
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

    async function show_CruiseMode_modal(CruiseMode_el) {
        function auto_close() {
            var el = document.getElementById('CruiseModeModal');
            var modal = bootstrap.Modal.getOrCreateInstance(el);
            if (modal) {
                modal.hide();
            }
        }
        var result = await CGI.AjaxGet("/cgi-bin/CruiseMode.cgi");
        setTimeout(auto_close, 30000);
        var dest = document.getElementById('CruiseModeModalBody');
        if (dest) {
            dest.innerHTML = result;
        }
    }

    var init = function() {
        // Attach events to buttons
        const CruiseMode_el = document.getElementById('CruiseModeModal');
        if (CruiseMode_el) {
            // 'show' triggered by clicking the button
            CruiseMode_el.addEventListener('show.bs.modal',
                show_CruiseMode_modal(CruiseMode_el));
        }
    };

    init();

})();

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
        AjaxPost: AjaxPost
    };

})();
