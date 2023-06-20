"""
    cgi-bin/secret.py

    Routines to handle validation of security for the SQLite GUI
"""

import jwt
import os
import sys
from datetime import datetime, timedelta

##############################################################################
##############################################################################
#
#     You should (probably) change the SECRET to something,
#     you know, .... *secret*.  And keep it that way.  Otherwise
#     anyone could generate their OWN jwt and you'd think it
#     was peachy.
#
##############################################################################
##############################################################################
# https://xkcd.com/936/
_SECRET = "correct horse battery staple"
#    LEN:"12345678901234567890123456789012"
# Ideally, SHA256 passwords/phrases *should* be at least 32 bytes


##############################################################################
def validate_token():
    """ Validate Authorization token

        We should have received a JWT (Javascript Web Token) in the
        Authorization header of the request.  Find it, validate it,
        and extract the username from the token payload.

        Returns the username or None.
    """

    auth_header = os.environ.get('HTTP_AUTHORIZATION', None)
    # Should be something like "Bearer [3 dot separated groups of Hex]
    if not auth_header:
        # print("No 'Authorization' header found", file=sys.stderr)
        return None

    auth_split = auth_header.split(' ')
    if len(auth_split) > 1:
        token = auth_split[1]
    else:
        # print("No Auth Token found", file=sys.stderr)
        return None
    payload = {}
    try:
        payload = jwt.decode(token, _SECRET, algorithms="HS256")
    except jwt.PyJWTError as err:
        # print("PyJWTError: ", err, file=sys.stderr)
        return None

    return payload.get('name', None)


##############################################################################
def validate_csrf(token):
    """ Validate a JWT used for CSRF protection

        CSRF tokens are passed as values of hidden form fields.  This
        routine is passed a JWT and attempts to validate it.  Unlike
        Django CSRF middleware, we send a fresh CSRF token on every
        request.  Django's tokens are valid for a *long* time.  Ours
        are good for the next two minutes, and are cryptographically
        signed (makeing them tougher to fake).

        Returns True or False (valid or invalid).
    """

    try:
        jwt.decode(token, _SECRET, algorithms="HS256")
    except jwt.PyJWTError as err:
        # expired tokens throw an exception, too.
        print(err, file=sys.stderr)
        return False
    else:
        return True


##############################################################################
def short_ttl_jwt(ttl=2):
    """ Build a short lived JWT for CSRF purposes

        We build a Javascript Web Token with a short time-to-live (by 
        default only 2 minutes) to get passed as a CSRF token when
        we send out a form.  2 minutes should give you a nice comfortable
        cushion to account for server and transmission delays and plenty
        of time for the user to dither about which option (if any) they
        want to select, but it's easy enough to change.

        ttl expressed in minutes
    """

    payload_data = {
        "name": 'CSRF Token',
        "exp": datetime.utcnow() + timedelta(minutes=ttl),
        "nbf": datetime.utcnow(),
        "iat": datetime.utcnow()
    }
    our_jwt = jwt.encode(payload_data,
                         _SECRET,
                         algorithm="HS256")
    return our_jwt
