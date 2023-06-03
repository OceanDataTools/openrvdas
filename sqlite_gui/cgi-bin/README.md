## CGI's for OpenRVDAS SQLite GUI

Requests that perform no change to the API are handled via the GET method.
These include things like listing cruise modes and logger modes, listing
files, etc.

Requests that will make changes to the API are handled by the POST method,
and require JWT authentication

We (currently) have:
```
LoggerMode.cgi
CruiseMode.cgi
Auth.cgi
FileBrowser.cgi
```

### LoggerMode.cgi
*GET* requests require a QUERY_STRING with the name of the logger, and
will return HTML that can be pasted into a form.
*POST* requests change the logger mode.

### CruiseMode.cgi
*GET* requests return HTML that can be pasted into a form
*POST* requests change the cruise mode.

### Auth.cgi
*GET* reqeusts return status code 204 and no content.
*POST* requestrequire a QUERY_STRING with the name of the logger, and
will return HTML that can be pasted into a form.
*POST* requests change the logger mode.

### CruiseMode.cgi
*GET* requests return HTML that can be pasted into a form
*POST* requests change the cruise mode.

### Auth.cgi
*GET* reqeusts return status code 204 and no 
*POST* requests take the supplied username/password, validate them,
and return JSON that will include `'jwt': <a jwt>`

#### Password Authentication
Currently we're storing the username/password key-value pairs using
python's `shelve` module.  Passwords are stored as SHA256 hashes.
The supplied password is hashed and compared to the stored hash.
Users are added/deleted/listed using the supplied `Usertool.py`
utility in this directory.

#### Debugging edits/upgrades
If the output isn't a valid HTML response (headers are bad, or
you start outputting something before printing the blank line
after the headers), fastcgi will toss a 502 error (Bad Gateway).
So it makes it tough, since you can't really see what's going
wrong.  STDERR from the scripts will go to 
`/var/log/openrvdas/fcgiwrap_stderr.log`.  That can be helpful.

### ROADMAP
Logger and CruiseMode could generate a short-lived JWT 
( 1 minute? ) delivered in the GET to be
returned as a hidden field in the POST.

when we want to load a config, we could pop up a confirmation
modal (again with a short-lived JWT).
