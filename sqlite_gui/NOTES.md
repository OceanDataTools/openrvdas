
### Install requirements for SQLITE UI

Need to `pip install pyjwt`
copy `openrvdas_sqlite.ini` to /etc/supervisor.d (or your distro equiv)
May or may not need to `chmod g+w /opt/openrvdas`.
May or may not need to `gpasswd -a nginx rvdas`
Need to check those two on a clean install...
Need to run the `CreateDatabse.sh` script to build a blank database.
Need to `cd cgi-bin` and run `UserTool.py`, add a user authorized to
make changes.
SSL cert/key go in the nginx directory.


### Running it

Using supervisor, stop `openrvdas:Logger_Manager`, `web:nginx`, `web:uwsgi`,
start the `SQLite` group (`sqlite.fcgiwrap`, `sqlite:logger_manager`, and
`sqlite:nginx_sqlite`). 
`api_tool.py` is sort of like the API command line tool, but whipped together
while I was working on the API so I could make sure I was doing it right.
Works interactively or one-shot with the command as an argument.

### ROADMAP
Code cleanups to the javascript (many of which could be applied to the
django GUI).
Our auth scheme is pretty good.  We could add a second (short-lived) JWT
to the CGI forms, and move the secret to a single file we pull in
at runtime (avoiding the need to edit each of the CGI files if we
want to change the secret)
Maybe better and/or more authorization schemes (PAM would probably be good).
Maybe better handling of errors from the CGI scripts.

