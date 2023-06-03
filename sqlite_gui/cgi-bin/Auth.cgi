#!/opt/openrvdas/venv/bin/python
"""
    cgi-bin/Auth.cgi

    Handles logging in/out in a secure (enough) manner.
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
    """ Called when this is accessed via the POST method """

    (headers, content, status) = process_post_request()

    if content:
        headers.append("Content-Type: text/json")

    for header in headers:
        print(header)
    print()

    if content:
        print(json.dumps(content, indent=2))
        if content.get('error', None):
            print(content, file=sys.stderr)


##############################################################################
def authenticate(form):
    # FIXME:  This needs to return a reason on failure
    #         User not found, passwords don't match
    """ extract username/password from form data,
        authenticate the user, return true or false
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

    name = form.get('username', 'nobody')
    # exp should be 90 days (I guess)
    payload_data = {
        "name": name,
        "exp": datetime.now() + timedelta(days=90),
        "iat": datetime.now()
    }
    # https://xkcd.com/936/
    our_jwt = jwt.encode(payload_data,
                         secret.SECRET,
                         algorithm="HS256")
    return our_jwt


##############################################################################
def process_post_request():
    """ Lower level processing for the post request.  I do it this way
        hoping to not output anything to stdout hoping that
        we won't get a 502 error.
    """

    content = {}
    cFS = cgi.FieldStorage()
    form = {}
    # Convert FieldStorage to a regular dict.  Easier.
    for key in cFS.keys():
        form[key] = cFS[key].value

    # Action should be one of 'login', 'logout'
    action = form.get('login_action', 'not specified')
    content['login_action'] = action
    # Authenitcate username/password against local list
    # See "Usertool.py"
    authenticated = authenticate(form)
    if authenticated:
        content['jwt'] = build_jwt(form)
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
