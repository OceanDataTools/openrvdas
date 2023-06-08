
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
Users are encouraged to change the passphrase in cgi-bin/secret.py  

### Running it
Using supervisor  
Stop the following (using the web interface or supervisorctl)   
- openrvdas:Logger_Manager  
- web:nginx  
- web:uwsgi  
Start the SQLite group (using the web interface or `supervisorctl start sqlite:*)`   
- sqlite.fcgiwrap  
- sqlite:logger_manager  
- sqlite:nginx_sqlite   
Configure the web interface (if desired) by modifying openrvdas.json,
and load a configuration, or use `api_tool.py` and commands for the 
ServerAPI.

### FUTURE ROADMAP
Code cleanups to the javascript  
- Encapsulate more globals  
- Class for the cruise mode button  
- Class for the ws message parsers  
Better and/or more authorization schemes (PAM would probably be good).  
Better handling of errors from the CGI scripts.  
Create an installation script.  
Figure out why database backups not working.  

### Non SQLite related changes
- pty data simulation (no more socat)
- 
