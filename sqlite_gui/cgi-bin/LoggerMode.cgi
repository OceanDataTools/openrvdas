#!/opt/openrvdas/venv/bin/python
"""
    cgi-bin/LoggerMode.cgi

    Handles request from the logger buttons.
    GET requests provide a list of logger config names for the logger.
    POST requests change the logger config to the selected config name
"""

import cgi
import cgitb
import sys
import os
from os.path import dirname, realpath
# import jwt
import secret

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from sqlite_gui.sqlite_server_api import SQLiteServerAPI as serverapi # noqa E402

api = serverapi()
cgitb.enable()


##############################################################################
def handle_get():
    """ Handles GET requests for the logger buttons

        Queries the API for a list of logger names, and returns HTML form
        fields with radio buttons to select the desired mode.  Adds a CSRF
        token.
    """

    # Send HTTP headers
    print("Content-Type: text/html;")
    print("Cache-Control: no-cache")
    print()

    # Get QUERY_STRING for logger_id
    # Send HTTP response body
    qs = os.environ.get("QUERY_STRING", None)
    SearchParams = [i.split('=') for i in qs.split('&')]
    logger_id = SearchParams[0][0]
    logger_conf = api.get_logger(logger_id)
    active_mode = None
    if 'active' in logger_conf:
        active_mode = logger_conf.get('active', None)
    if 'configs' not in logger_conf:
        Q = "<h3>'configs' not in configuration</h3>"
        print(Q)
        return
    modes = logger_conf.get('configs', None)
    for mode in modes:
        print('<div class="form-check" style="padding-left: 3em">')
        print('<input class="form-check-input" type="radio" ')
        print('name="radios" ')
        print('id="%s_radioButton" ' % mode)
        if mode == active_mode:
            print('checked=true ')
        print('value="%s">' % mode)
        print('<label class="form-check-label" ')
        print('for="%s_radioButton"' % mode)
        print('text="%s">%s</label></div>' % (mode, mode))
    Q = '<input type="hidden" name="logger_id" value="%s">' % logger_id
    print(Q)
    sl_jwt = secret.short_ttl_jwt()
    Q = '<input type="hidden" name="CSRF" value="%s">' % sl_jwt
    print(Q)


##############################################################################
def handle_post():
    """ POST request handler for the logger buttons

        Calls a helper function to perform the action, then outputs the
        data provided.
    """

    (headers, content, status) = process_post_request()

    headers.append('Status: %s' % status)
    if content:
        headers.append("Content-Type: text/json")

    for header in headers:
        print(header)
    print()

    if content:
        content['ok'] = 1 if 'error' in content else 0
        print(content)


##############################################################################
def process_post_request():
    """ Does the actual processing for the POST requests

        Parses the form data to extract the required fields, authenticates
        the user, checks the validity fot the CSRF token, authenticates the
        user, calls the API to set the desired logger mode, then logs the
        mode change to the API messagelog.
    """

    content = {}
    cFS = cgi.FieldStorage()
    form = {}
    # Convert FieldStorage to a regular dict.  Easier.
    for key in cFS.keys():
        form[key] = cFS[key].value

    # CSRF protection
    sl_jwt = form.get('CSRF', None)
    if not sl_jwt:
        print("No sl_jwt found", file=sys.stderr)
        content['error'] = "CSRF check failed"
        return ([], content, 403)

    if not secret.validate_csrf(sl_jwt):
        print("CSRF NOT VALID", file=sys.stderr)
        content['error'] = "CSRF check failed"
        return ([], content, 403)

    # Make sure we're authorized to do this
    username = secret.validate_token()
    if not username:
        content['error'] = 'Login Required'
        return ([], content, 401)

    # Do the thing
    mode = form.get('radios', 'not specified')
    logger_id = form.get('logger_id', None)
    if logger_id is None:
        Q = 'No logger_id found in form fields'
        content['error'] = Q
        return ([], content, 418)

    logger_conf = api.get_logger(logger_id)
    if 'configs' not in logger_conf:
        Q = 'configs not in logger_conf'
        content['error'] = Q
        return ([], content, 412)
    modes = logger_conf.get('configs', None)
    try:
        # if mode in modes
        if mode in modes:
            api.set_active_logger_config(logger_id, mode)
        else:
            Q = 'mode "%s" not in config for logger "%s"' % (mode, logger_id)
            content['error'] = Q
            return ([], content, 405)
    except Exception as err:
        Q = "api.set_active_logger_config(%s): %s" % (mode, err)
        content['error'] = Q
        return ([], content, 405)
    else:
        # NOTE(KPED): Do we want to query the API to be sure
        #             the change took?  Not thrilled that the
        #             API doesn't return success/fail.
        Q = 'Changing %s mode to %s' % (logger_id, mode)
        api.message_log('Web GUI', username, 3, Q)
        content['message'] = Q

    return ([], content, 200)


##############################################################################
if __name__ == "__main__":
    method = os.environ.get("REQUEST_METHOD", None)
    if method == "GET":
        try:
            handle_get()
        except Exception as err:
            print("Error displaying form: %s", err, file=sys.stderr)
    elif method == "POST":
        try:
            handle_post()
        except Exception as err:
            print("Error processing form: %s", err, file=sys.stderr)
    else:
        # Command line
        handle_post()
