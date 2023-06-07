#!/opt/openrvdas/venv/bin/python
"""
    cgi-bin/Template.cgi

    Template for our CGI scripts.
    NOTE:  The CGI module is deprecated in Python 3.11, so for forward
           compatibility we need to start replacing it now.
"""

import sys
import os
import secret
# from os.path import dirname, realpath

# sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
# from sqlite_gui.sqlite_server_api import SQLiteServerAPI as serverapi # noqa E402


##############################################################################
def read_query_string():
    """ Read QUERY_STRING and parse it into a dictionary """

    form = {}
    qs = os.environ.get("QUERY_STRING", None)
    print('qs = %s' % qs, file=sys.stderr)
    SearchParams = [i.split('=') for i in qs.split('&')]
    print('SearchParams = %s' % SearchParams, file=sys.stderr)
    for iSplits in SearchParams:
        if len(iSplits) > 1:
            form[iSplits[0]] = iSplits[1]
        else:
            form[iSplits[0]] = ''
    return form

# Content-Type  =  multipart/form-data; boundary=----WebKitFormBoundarytorpL8tdJ19HcPXj

##############################################################################
def read_form():
    """ Reads formdata and/or QUERY_STRING and returns form data
        formatted as a regular dictionary.  The CGI module is
        deprecated, so this function exists mainly so we can
        work on a replacement """

    form = {}
    files = {}
    method = os.environ.get('REQUEST_METHOD', None)

    if method == "GET":
        form = read_query_string()
    if method == "POST":
        ct = os.environ.get('CONTENT_TYPE', None)
        if '; boundary=' not in ct:
            print("No boundary.  We're screwed", file=sys.stderr)
        if 'multipart/form-data' not in ct:
            print("Not multipart/form-data.  We're screwed", file=sys.stderr)
        boundary = ct.split('=')[1]
        body = ""
        parts = []
        part = ""
        for line in sys.stdin:
            if boundary in line:
                parts.append(part)
                part = ""
            else:
                part = part + line
            body = body + line
        for part in parts:
            lines = part.split('\n')
            if 'Content-Disposition: form-data' in lines[0]:
                lines.pop(-1)
                lines.pop(1)
                s = lines[0].split('=')
                key = s[1].strip()
                if key[0] == '"':
                    key = key[1:-1]
                value = lines[1].strip()
                form[key] = value
        
    print("Printing out form{}", file=sys.stderr)
    for key in form:
        print(key, ' = ', form[key], file=sys.stderr)
    print("...Done", file=sys.stderr)
    return form


##############################################################################
def handle_get():
    """ Called when this is accessed via the GET HTTP method """

    # Send HTTP headers
    print('Content-Type: text/html;')
    print()

    # Get form data
    form = read_form()

    # Do the thing
    print("content goes here %s" % form)

    # Add CSRF Token to form
    sl_jwt = secret.short_ttl_jwt()
    Q = '<input type="hidden" name="CSRF" value="%s" .>' % sl_jwt
    print(Q)


##############################################################################
def handle_post():
    """ Called when this is accessed via the POST HTTP method """

    # we only include headers because... you know...
    # maybe Set-Cookie, maybe Last-Modified...
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

    # Parse form data
    form = read_form()

    # CSRF Protection (goes here)
    sl_jwt = form.get('CSRF', None)
    if not sl_jwt:
        content['ok'] = 0
        content['error'] = 'CSRF token not found'
        # print("CSRF Token not found", file=sys.stderr)
        # for key in form:
        #    print('%s = %s' % (key, form.get(key, '<No Value>')),
        #          file=sys.stder
        return ([], content, 401)

    if not secret.validate_csrf(sl_jwt):
        print("CSRF NOT VALID", file=sys.stderr)
        content['ok'] = 0
        content['error'] = 'CSRF token invalid or expired'
        return ([], content, 401)

    # Make sure we're authorized to do this
    username = secret.validate_token()
    if not username:
        content['ok'] = 'false'
        content['error'] = 'Login Required'
        return (headers, content, 401)

    # Do the thing
    try:
        # Some ServerAPI stuff or something
        content['whatever'] = "whatever"
    except Exception as err:
        content['ok'] = 0
        content['error'] = str(err)
        return ([], content, 418)

    # Done doing the thing
    if True:     # This is how we return success
        content['ok'] = 1
        return ([], content, 200)
    if False:    # This is how we return failure
        content['ok'] = 0
        content['error'] = "some error message"
        """ Some HTTP error codes you might like:
        400 - Bad Request    412 - Precondition failed
        401 - Unauthorized   418 - I am a teapot (not joking)
        403 - Forbidden      451 - Unavailable for legal reasons
        """
        return ([], content, 451)  # Pick an error code


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
            print("Error processing form: %s" % err, file=sys.stderr)
    else:
        # Command line for debugging
        handle_post()
