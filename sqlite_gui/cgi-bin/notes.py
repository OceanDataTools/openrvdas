#!/usr/bin/env python3
"""
    notes.py

    CGI to work on stuff.
    Need to develop a... I guess we'll call it a "template" for CGI
    that wont give us "BAD GATEWAY" errors are the drop of a hat

"""

import cgi
import cgitb
#import SQLiteServerAPI
import os
import sys
#from datetime import datetime
import json
from os.path import dirname, realpath

# FIXME:  Figure out where we put these so we can get
#         relative path to /opt/openrvdas/server
#         so we can import the sqlite thingee
#from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))

#from server.server_api import ServerAPI
sys.path.append('/opt/openrvdas/venv/lib/python3.8/site-packages')
from server.sqlite_server_api import SQLiteServerAPI

cgitb.enable()

# api methods
########################
# get_configuration
# get_modes
# get_active_mode
# get_default_mode
# get_loggers
# get_logger_config(config_name)
# get_logger_configs(mode=None) # default active mode
# get_logger_config_name(logger_id, mode=None) # default active mode
# get_logger_config_names(logger_id) # get list of mode names for logger'
# set_active_mode(mode)
# set_active_logger_config(logger, config_name)

# 
# Get some example CGI's and template these
#
#FIXME:  This is python2, need python3
# Print other headers (like cookie), then Content-type

# Setting Cookies
#print("Set-Cookie:UserID = XYZ;\r\n")
#print("Set-Cookie:Password = XYZ123;\r\n")
#print("Set-Cookie:Expires = Tuesday, 31-Dec-2007 23:12:40 GMT;\r\n")
#print("Set-Cookie:Domain = www.tutorialspoint.com;\r\n")
#print("Set-Cookie:Path = /perl;\n")
## Other headers can go here
#print("Content-Type: text/html")    # HTML is following
#print()                             # blank line, end of headers
#print("<html>")
#print("<head>")
#print("<title>Text Area - Fifth CGI Program</title>")
#print("</head>")
#print("<body>")
#text_content = "This is our text content"
#print("<h2> Entered Text Content is %s</h2>" % text_content)
#print("</body>")

try:
    cgi.test()
    print('<br /><h3>Environment Vars</h3>');
    for k, v in os.environ.items():
        print(f'{k} = {v}<br />')
except Exception as err:
    print("Content-Type: text/html")
    print()
    print("Error: ", err)

#cgitb.enable()
#api = SQLiteServerAPI()
#cruise = api.get_configuration()
#j = json.dumps(cruise, indent=2)

# Reading cookies
#if os.getenv('HTTP_COOKIE') is not None:
#    for cookie in map(strip, split(environ['HTTP_COOKIE'], ';')):
#        (key, value ) = split(cookie, '=');
#        if key == "UserID":
#            user_id = value or None
#            print("User ID  = %s" % user_id)
#
#        if key == "Password":
#            password = value or None
#            print("Password = %s" % password)

# Reading form data
# Create instance of FieldStorage 

# Get data from form-fields
#form = cgi.FieldStorage()
#if "name" not in form or "addr" not in form:
#    print("<H1>Error</H1>")
#    print("Please fill in the name and addr fields.")
#else:
#    print("<p>name:", form["name"].value)
#    print("<p>addr:", form["addr"].value)
#value = form.getlist("username") or []
#usernames = ",".join(value)

# Environment

#e = os.environ
#for key in e:
#    print("%s ==> %s" % (key, e[key]))

# HTTP headers of interest
# Cookies, Referer>

# Modes should be "off, In-Port, EEZ, Logging, Palmer"
# In port runs all->net except (water/tsonar)
# EEZ Runs all->net
# Logging is all->write
# Palmer is all->write except water/sonar
