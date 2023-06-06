#!/usr/bin/env python
"""
    ${OPENRVDAS}/cgi-bin/Usertool.py

    Manages list of users authorized to make changes to the API via
    the SQLite API web interface.

    Verbs:
    -a, -add,       Add a user
    -d, --delete,   Delete a user
    -l, --list,     List users

    -u/--user <username>
    -p/--passwd <plain text passwd>
"""

import argparse
import hashlib
import shelve

DBFILE = './passwd/passwd-ish'


##############################################################################
def add_user(config):
    """ Add user to the persistent store """
    username = config.get('user', None)
    password = config.get('password', None)

    if not username:
        print('You have to supply a username')
        return
    if not password:
        print("You have to supply a password")
        return

    hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()
    with shelve.open(DBFILE) as db:
        db[username] = hashed

    return


##############################################################################
def delete_user(config):
    """ Delete a user from the persistent store """
    username = config.get('user', None)

    if not username:
        print('you have to supply a username')
        return

    with shelve.open(DBFILE) as db:
        del db[username]


##############################################################################
def list_users():
    """ list users in the persistent store """

    with shelve.open(DBFILE) as db:
        klist = list(db.keys())
        for user in klist:
            print("%s: %s" % (user, db[user]))


##############################################################################
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
                 prog='Usertool',
                 description='Maintains user/pass for SQLite GUI')
    parser.add_argument('-a', '--add',
                        action='store_true',
                        help="Add user")
    parser.add_argument('-d', '--delete',
                        action='store_true',
                        help="Delete user")
    parser.add_argument('-l', '--list',
                        action='store_true',
                        help="List users")
    parser.add_argument('-u', '--user', help="Username")
    parser.add_argument('-p', '--password', help="Password")
    args = parser.parse_args()
    config = vars(args)

    if config['add']:
        add_user(config)
    elif config['delete']:
        delete_user(config)
    elif config['list']:
        list_users()
    else:
        print("You might want to pick one of add, list, or delete")
