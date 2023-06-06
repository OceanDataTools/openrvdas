#!/opt/openrvdas/venv/bin/python
"""
    cgi-bin/LoggerMode.cgi

    Handles GET/POST requests associated with logger buttons on
    the OpenRVDAS GUI (SQLite version).
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
# def validate_token():
#    """ We should have received a JWT in the Authorization header.
#        Validate it.
#    """
#
#    our_secret = secret.SECRET
#    auth_header = os.environ.get('HTTP_AUTHORIZATION', None)
#    if not auth_header:
#        return None
#
#    auth_split = auth_header.split(' ');
#    if len(auth_split) > 1:
#        token = auth_split[1]
#    else:
#        return None
#    payload = {}
#    try:
#        payload = jwt.decode(token, our_secret, algorithms="HS256" )
#    except jwt.PyJWTError as err:
#        print("PyJWTError: ", err, file=sys.stderr)
#        return None
#
#    return payload.get('name', None)


##############################################################################
def handle_get():
    """ Called when this is accessed via the GET HTTP method """

    # Send HTTP headers
    print("Content-Type: text/html;")
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


##############################################################################
def handle_post():
    """ Called when this is accessed via the POST HTTP method """

    (headers, content, status) = process_post_request()

    headers.append('Status: %s' % status)
    if content:
        headers.append("Content-Type: text/json")

    for header in headers:
        print(header)
    print()

    if content:
        print(content)
        if content.get('error', None):
            print(content, file=sys.stderr)
    else:
        print('{}')


##############################################################################
def process_post_request():
    headers = []
    content = {}
    cFS = cgi.FieldStorage()
    form = {}
    # Convert FieldStorage to a regular dict.  Easier.
    for key in cFS.keys():
        form[key] = cFS[key].value

    mode = form.get('radios', 'not specified')
    logger_id = form.get('logger_id', None)
    if logger_id is None:
        Q = 'No logger_id found in form fields'
        content = {'ok': 'false', 'error': Q}
        return (headers, content, 418)

    # Make sure we're authorized to do this
    username = secret.validate_token()
    if not username:
        content['ok'] = 'false'
        content['error'] = 'Login Required'
        return (headers, content, 401)

    logger_conf = api.get_logger(logger_id)
    if 'configs' not in logger_conf:
        Q = 'configs not in logger_conf'
        content = {'ok': 'false', 'error': Q}
        return (headers, content, 412)
    modes = logger_conf.get('configs', None)
    try:
        # if mode in modes
        if mode in modes:
            api.set_active_logger_config(logger_id, mode)
            Q = 'Changing %s mode to %s' % (logger_id, mode)
            api.message_log('Web GUI', username, 3, Q)
        else:
            Q = 'mode "%s" not in config for logger "%s"' % (mode, logger_id)
            content = {'ok': 'false', 'error': Q}
            return (headers, content, 405)
    except Exception as err:
        Q = "api.set_active_logger_config(%s): %s" % (mode, err)
        content = {'ok': 'false', 'error': Q}
        return (headers, content, 405)
    else:
        content = {'ok': 'true',
                   'status_text': 'logger mode changed to %s' % mode}

    return (headers, content, 200)


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
