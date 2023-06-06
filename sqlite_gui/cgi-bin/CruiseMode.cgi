#!/opt/openrvdas/venv/bin/python
"""
    cgi-bin/CruiseMode.cgi

    Escript that handles GET/PUT for changing logger manager mode
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
    """ Called when this is accessed via the GET HTTP method """

    # Send HTTP headers
    print("Content-Type: text/html;")
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
# def validate_token():
#    """ We should have received a JWT in the Authorization header.
#        Validate it.
#    """

#    our_secret = secret.SECRET
#    auth_header = os.environ.get('HTTP_AUTHORIZATION', None)
#    if not auth_header:
#        return (False, 'nobody')
#
#    auth_split = auth_header.split(' ');
#    if len(auth_split) > 1:
#        token = auth_split[1]
#    else:
#        return (False, 'nobody')
#    payload = {}
#    try:
#        payload = jwt.decode(token, our_secret, algorithms="HS256" )
#    except jwt.PyJWTError as err:
#        print("PyJWTError: ", err, file=sys.stderr)
#        return (False, 'nobody')
#
#    username = payload.get('name', None)
#    if not username:
#        return (False, 'nobody')
#
#    return (True, username)


##############################################################################
def process_post_request():
    """ Lower level handler for the POST request """

    headers = []
    content = {}

    # Handle form fields
    form = {}
    fs = cgi.FieldStorage()
    for key in fs.keys():
        form[key] = fs[key].value

    mode = form.get('radios', 'not specified')
    username = secret.validate_token()
    if not username:
        content['ok'] = 0
        content['error'] = 'Login Required'
        return (headers, content, 401)

    try:
        modes = api.get_modes()
        # Silly, but test anyway
        if mode in modes:
            api.set_active_mode(mode)
        else:
            content['ok'] = 0
            content['error'] = 'Mode %s not allowed' % mode
            return (headers, content, 406)
    except Exception as err:
        Q = "Exception in api.set_active_modes(%s): %s" % (mode, err)
        content['ok'] = 0
        content['error'] = Q
        return (headers, content, 406)

    # Add mode change to the message log
    Q = 'Changing cruise mode to %s' % mode
    try:
        api.message_log('Web GUI', username, 3, Q)
    except Exception:
        pass

    return (headers, content, 200)


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
