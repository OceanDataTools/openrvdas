#!/opt/openrvdas/venv/bin/python
"""
    cgi-bin/Template.cgi

    Template for our CGI scripts.
    NOTE:  The CGI module is deprecated in Python 3.11, so for forward
           compatibility we need to start replacing it now.
"""

import cgi
import cgitb
import sys
import os
import jwt
import secret
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from sqlite_gui.sqlite_server_api import SQLiteServerAPI as serverapi # noqa E402

api = serverapi()
cgitb.enable()

##############################################################################
def read_form():
    """ Reads formdata and/or QUERY_STRING and returns form data 
        formatted as a regular dictionary.  The CGI module is 
        deprecated, so this function exists mainly so we can
        work on a replacement """

    # Convert CGI module FieldStorage to a regular dict.
    qs = os.environ.get("QUERY_STRING", None)
    if qs is None:
        qs = ""
        for line in sys.stdin:
            qs = qs + line
    print('qs = %s' % qs, file=sys.stderr)
    return {}

    SearchParams = [i.split('=') for i in qs.split('&')]
    print('SearchParams = %s' % SearchParams, file=sys.stderr)
    for iSplits in SearchParams:
        if len(iSplits) > 1:
            form[iSplits[0][ = iSplits[1]
        else:
            form[iSplits[0]] = ''

    print("read_form: form = %s", form, file=sys.stderr)

    form = {}
    cFS = cgi.FieldStorage()
    for key in cFS.keys():
        form[key] = cFS[key].value

    return form


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
    username = validate_jwt()
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
            res = api.set_active_logger_config(logger_id, mode)
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
            print("Error displaying form: %s" % err, file=sys.stderr)
    elif method == "POST":
        try:
            handle_post()
        except Exception as err:
            print("Error processing form: %s", err, file=sys.stderr)
    else:
        # Command line
        handle_post()
