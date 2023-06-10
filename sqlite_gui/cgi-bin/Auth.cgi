#!/opt/openrvdas/venv/bin/python
"""
    cgi-bin/Auth.cgi

    Handles login a secure (enough) manner.

    The provided password is hashed and oompared against the hash stored
    in a Shelf for the provided username.  If the hashes match, the password
    is accepted and a JWT is constructed valid for 90 days.   The client
    returns that JWT in the Authorization header of subsequent requests.

    Since this authentication scheme is stateless, we don't need to store
    the token on the server side.  A client can log out by the simple
    expedient of forgetting the JWT.
"""

import cgi
import sys
import os
import jwt
import json
import shelve
import hashlib
from datetime import datetime, timedelta
import secret


##############################################################################
def handle_post():
    """ Called when this is accessed via the POST method.

        The message body is constructed by a helper routine
        that returns a dictionary, and that dictionary is
        returned to the calling page as JSON
    """

    header = []
    content = {}
    status = 999
    try:
        (headers, content, status) = process_post_request()
    except Exception as err:
        content['ok'] = 0
        content['error'] = str(err)

    headers.append('Status: %s' % status)
    if content:
        headers.append("Content-Type: text/json")

    for header in headers:
        print(header)
    print()

    if content:
        content['ok'] = 0 if 'error' in content else 1
        print(content)
        if not content.get('ok', 0):
            print(content, file=sys.stderr)
    else:
        print({})


##############################################################################
def authenticate(form):
    # FIXME:  This needs to return a reason on failure
    #         User not found, passwords don't match
    """ Extract username/password from form data, authenticate the user,
        return true or false
    """

    DB_FILE = "./passwd/passwd-ish"
    action = form.get('login_action', 'none')
    if not action == "login":
        return False
    username = form.get('username', 'nobody')
    password = form.get('password', None)

    # Get
    with shelve.open(DB_FILE) as db:
        try:
            stored_passwd = db[username]
        except KeyError:
            stored_passwd = None
        if not stored_passwd:
            print("Password for %s not found in passwd-ish" % username,
                  file=sys.stderr)
            return False
        h1 = hashlib.sha256(password.encode('utf-8')).hexdigest()
        if not h1 == stored_passwd:
            print("Passwords for user %s do not match" % username,
                  file=sys.stderr)
            return False

    return True


##############################################################################
def build_jwt(form):
    """ Build a JWT for an authenticated user """
    # NOTE(Kped): Should this be moved to secret.py ??

    name = form.get('username', 'nobody')
    # exp should be 90 days (I guess)
    payload_data = {
        "name": name,
        "exp": datetime.now() + timedelta(days=90),
        "iat": datetime.now()
    }
    our_jwt = jwt.encode(payload_data,
                         secret._SECRET,
                         algorithm="HS256")
    return our_jwt


##############################################################################
def process_post_request():
    """ Look in formdata for requeired fields (username/password),
        authenticates the credentials, and if successful provides a
        token to be returned to the user.  Ouput is provided in the
        form of a dictionary.
    """

    content = {}
    cFS = cgi.FieldStorage()
    form = {}
    # Convert FieldStorage to a regular dict.  Easier.
    for key in cFS.keys():
        form[key] = cFS[key].value

    username = authenticate(form)
    if username:
        content['jwt'] = build_jwt(form)
        content['message'] = "User %s authenticate" % username
    else:
        content['error'] = "Not authenticated"

    return ([], content, 200)


if __name__ == "__main__":
    method = os.environ.get("REQUEST_METHOD", None)
    if method == "GET":
        # We have no reason to reply to GET, but...
        print("Content-Type: text/html;")
        print('Status: 204')
        print()
    elif method == "POST":
        try:
            handle_post()
        except Exception as err:
            print("Content-Type: text/json;")
            print("Status: 418")
            print()
            print(json.dumps(err))
            print("Error processing form: %s" % err, file=sys.stderr)
    else:
        # Command line (for testing)
        handle_post()
