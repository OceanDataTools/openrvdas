#!/opt/openrvdas/venv/bin/python
"""
    cgi-bin/CruiseMode.cgi

    Script that handles GET/PUT for changing logger manager mode GET
    request return HTML with form fields enumerating the cruise modes
    known to the API.  Hidden fields include a JWT for CSRF protection.

    POST requests change the cruise mode via the API and log the change
    to the API messagelog.
"""

import cgi
import cgitb
import sys
import os
# import jwt
from os.path import dirname, realpath
import secret

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
# from django_gui.django_server_api import DjangoServerAPI as serverapi
# from server.in_memory_server_api import InMemoryServerAPI as serverapi
from sqlite_gui.sqlite_server_api import SQLiteServerAPI as serverapi # noqa E402

api = serverapi()
cgitb.enable()


##############################################################################
def handle_get():
    """ GET handler for CruiseMode

        Queries the API for a list of modes and returns HTML
        form radio buttons to select one.
    """

    # Send HTTP headers
    print("Content-Type: text/html")
    # See https://www.rfc-editor.org/rfc/rfc7234#section-5.2.1.5
    print("Cache-Control: no-store")
    print()

    # Send HTTP response body
    modes = api.get_modes()
    active_mode = api.get_active_mode()
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
    sl_jwt = secret.short_ttl_jwt()
    Q = '<input type="hidden" name="CSRF" value="%s">' % sl_jwt
    print(Q)


##############################################################################
def handle_post():
    """ POST handler for CruiseMode

        Calls a helper function to do the actual processing, then outputs
        the returned information.
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
        if content.get('error', None):
            print(content, file=sys.stderr)
    else:
        print('{}')


##############################################################################
def process_post_request():
    """ Processes the post request and returns data for output.

        Parses form data, checks authentication, checks CSRF,
        call the API to set the desired mode, and logs the
        change to the API messagelog.
    """

    content = {}

    # Handle form fields
    form = {}
    fs = cgi.FieldStorage()
    for key in fs.keys():
        form[key] = fs[key].value

    mode = form.get('radios', 'not specified')
    username = secret.validate_token()
    if not username:
        content['error'] = 'Login Required'
        return ([], content, 401)

    # CSRF Protection
    sl_jwt = form.get('CSRF', None)
    if not sl_jwt:
        content['error'] = 'CSRF token not found'
        return ([], content, 403)

    if not secret.validate_csrf(sl_jwt):
        content['error'] = 'CSRF not valid'
        return ([], content, 403)

    # Do the thing
    try:
        modes = api.get_modes()
        # Silly, but test anyway
        if mode in modes:
            api.set_active_mode(mode)
        else:
            content['error'] = 'Mode %s not allowed' % mode
            return ([], content, 406)
    except Exception as err:
        Q = "Exception in api.set_active_modes(%s): %s" % (mode, err)
        content['error'] = Q
        return ([], content, 406)

    # NOTE)Kped): Query API for current mode to confirm ??
    # Add mode change to the message log
    Q = 'Changing cruise mode to %s' % mode
    try:
        api.message_log('Web GUI', username, 3, Q)
    except Exception:
        pass

    content['message'] = Q

    return ([], content, 200)


##############################################################################
if __name__ == "__main__":
    method = os.environ.get("REQUEST_METHOD", None)
    qs = os.environ.get("QUERY_STRING", None)
    if method == "GET":
        try:
            handle_get()
        except Exception as err:
            # This will show up in /var/log/openrvdas/fcgiwrap_stderr.log
            print("Error displaying form: %s" % err, file=sys.stderr)
    elif method == "POST":
        try:
            handle_post()
        except Exception as err:
            # This will show up in /var/log/openrvdas/fcgiwrap_stderr.log
            print("Error processing form: %s" % err, file=sys.stderr)
    else:
        # Command line
        handle_post()
