# OpenRVDAS Installation Guide
At the time of this writing OpenRVDAS has been built and tested against MacOS X, CentOS 7-9, Rocky 8-9, Ubuntu 18-23
and Raspbian operating systems. It may be possible to build against other Linux-based operating systems, and guides
will be added here as they are verified and documented.

You will need to be able to run the ``sudo`` command. To begin installation, grab the script from Github and run from
the command line using the following commands:
```
OPENRVDAS_REPO=raw.githubusercontent.com/oceandatatools/openrvdas
BRANCH=master
curl -O -L https://$OPENRVDAS_REPO/$BRANCH/utils/install_openrvdas.sh
chmod +x install_openrvdas.sh
sudo ./install_openrvdas.sh
```
selecting ``master``, ``dev`` or other branch of the repo if your project has one.

The script must be run as a user that has sudo permissions (the script will prompt several times
for the sudo password when needed). It will ask a lot of questions and provide default answers in parens that will be filled in if you hit "return"; without any other input:

############################################################################

```
OpenRVDAS configuration script
Name to assign to host (lmg-dast-s1-t)?
Hostname will be 'lmg-dast-s1-t'
Install root? (/opt)
Install root will be '/opt'
```

_Script will next ask which code repo and branch to use. Use the default
repo and branch unless you have a project-specific branch in mind (e.g. "usap").
If you need to access the internet via a proxy (as shown below), enter it when
asked; otherwise just hit return._

```
Repository to install from? (http://github.com/oceandatatools/openrvdas)
Repository branch to install? (master)
HTTP/HTTPS proxy to use (http://proxy.lmg.usap.gov:3128)?
Setting up proxy http://proxy.lmg.usap.gov:3128
Will install from github.com
Repository: 'http://github.com/oceandatatools/openrvdas'
Branch: 'master'
```

_Script will try to create the rvdas user under which the system will run. 
It won't mind if the user already exists (note: under MacOS, script is not
yet able to create a new user and will prompt you for a pre-existing user
name to use):_

```
OpenRVDAS user to create? (rvdas)
Checking if user rvdas exists yet
User exists, skipping
```

_By default, anyone can access the OpenRVDAS Django console as a viewer. But to load configurations or
change logger states you must be logged in. The system will create a login for the OpenRVDAS user
created above, but will use a password different from the user's system password to provide access
to OpenRVDAS. The system will prompt for that password now:_

```
Django/database password to use for user rvdas? (rvdas) 
```

_OpenRVDAS can use SSL and HTTPS for web access if desired. If you respond 'yes', to the question of whether to use
SSL, the script will prompt you to either create or provide the locations of .key and .crt files._

```
#####################################################################
OpenRVDAS can use SSL via secure websockets for off-server access to web
console and display widgets. If you enable SSL, you will need to either
have or create SSL .key and .crt files.

If you create a self-signed certificate, users may need to take additional
steps to connect to the web console and display widgets from their machines'
browsers. For guidance on this, please see the secure_websockets.md doc in
this project's docs subdirectory.

Use SSL and secure websockets?  (no) 
```
_By default, the OpenRVDAS web console will be served on port 80 (or 442 if using SSL). The script will prompt whether
you want to use an alternate port._
````
Port on which to serve web console? (80) 
````
_The script will prompt whether you want to run OpenRVDAS automatically (i.e. on boot) or manually. If your server is
running on dedicated machine (or VM) you'll probably want to answer 'yes'; if you're running it on your personal
to try things out, you should probably answer 'no' and start/stop the servers manually via `supervisorctl start all` and 
`supervisorctl stop all`._
```
#####################################################################
The OpenRVDAS server can be configured to start on boot. If you wish this
to happen, it will be run/monitored by the supervisord service using the
configuration file in /etc/supervisord.d/openrvdas.ini.

If you do not wish it to start automatically, it may still be run manually
from the command line or started via supervisor by running supervisorctl
and starting processes logger_manager and cached_data_server.

Start the OpenRVDAS server on boot?  (yes) 
```

_OpenRVDAS provides a test script that can be used to run a sample cruise configuration on stored test data. If you
are installing OpenRVDAS to try it out, you probably want to install this script. Again, whether or not you have it
run on boot will depend on whether or not your installation is on a dedicated machine._

_Note that this script may be disabled
by commenting out or deleting the `openrvdas_simulate.[ini,conf]` file in the supervisord configuration directory
(variously `/usr/local/etc/supervisor.d/`, `/etc/supervisord.d` or `/etc/supervisor/conf.d`, depending on which
OS distribution you are using)._
```
#####################################################################
For test installations, OpenRVDAS can configure simulated inputs from
stored data, which will allow you to run the "NBP1406_cruise.yaml"
configuration out of the box. This script will be configured to run
under supervisord as "simulate:simulate_nbp".

Do you want to install this script? (yes) 
Run simulate:simulate_nbp on boot? (no) 
```

_Users may optionally decide to **not** install the default web console if they wish to operate OpenRVDAS from the
command line. First-timers are encouraged to go with the default and install the web console._

```#####################################################################
The full OpenRVDAS installation includes a web-based console for loading
and controlling loggers, but a slimmed-down version of the code may be
installed and run without it if desired for portability or computational
reasons.

Install OpenRVDAS web console GUI?  (yes) 
```
_The OpenRVDAS scripts are controlled by the supervisor daemon. The daemon may be managed either from the command line
via the `supervisorctl` command or, optionally, via a web server._
```
#####################################################################
The supervisord service provides an optional web-interface that enables
operators to start/stop/restart the OpenRVDAS main processes from a web-
browser.

Enable Supervisor Web-interface?  (yes) 
Port on which to serve web interface? (9001) 
Would you like to enable a password on the supervisord web-interface?

Enable Supervisor Web-interface user/pass?  (no)
```

At this point, the script will run a while and, if all has gone well, wish you "Happy logging" when it has completed.
Whew.

## Post-Installation

The installation should allow you to connect via http to the server at the name you specified at the start of the script (e.g. ``lmg-dast-s1-t``). If you want to connect using any other names, e.g. the fully-qualified domain name ``lmg-dast-s1-t.lmg.usap.gov``, you'll need to add it to the Django server settings file in ``django_gui/settings.py``:

```
ALLOWED_HOSTS = [HOSTNAME, 'localhost', HOSTNAME + '.lmg.usap.gov']
```
If you make this change, you will want to restart the Django-based services:

```
supervisorctl restart django:*
```

If you wish to use InfluxDB and Grafana to create dashboards and display data, you
will need to run the installation script in `utils/install_influxdb.sh`. Please
see and follow the instructions in [Grafana/InfluxDB-based Displays](docs/grafana_displays.md).

## Starting and Stopping Servers

In addition to the NGINX webserver (and its Python helper interface UWSGI), OpenRVDAS relies on two servers: ``logger_manager.py`` and ``cached_data_server.py`` (see [Controlling Loggers](docs/controlling_loggers.md) for details). 

The easiest way to manage these servers is via the supervisord package that is installed by the installation script. If you answered 'yes' when asked whether OpenRVDAS should start automatically on boot up, supervisord will start them for you; if you answered 'no', the supervisord configurations will have still be created, but you will need to manually tell supervisord to start/stop them.

You can do this two ways, either via the local webserver at [http://openrvdas:9001](http://openrvdas:9001) (assuming your machine is named 'openrvdas') or via the command line ``supervisorctl`` tool:

```
(venv) rvdas@openrvdas:/opt/openrvdas$ supervisorctl
cached_data_server               RUNNING   pid 2045550, uptime 0:00:49
django:nginx                     RUNNING   pid 2045639, uptime 0:00:35
django:uwsgi                     RUNNING   pid 2045640, uptime 0:00:35
logger_manager                   RUNNING   pid 2045548, uptime 0:00:50
simulate:simulate_nbp            RUNNING   pid 2045646, uptime 0:00:35

supervisor> stop all
django:nginx: stopped
cached_data_server: stopped
django:uwsgi: stopped
logger_manager: stopped

supervisor> start logger_manager cached_data_server
logger_manager: started
cached_data_server: started

supervisor> status
cached_data_server               RUNNING   pid 2045739, uptime 0:00:04
django:nginx                     STOPPED   Jan 21 05:27 PM
django:uwsgi                     STOPPED   Jan 21 05:27 PM
logger_manager                   RUNNING   pid 2045714, uptime 0:00:05
simulate:simulate_nbp            STOPPED   Jan 21 05:27 PM

supervisor> start all
django:nginx: started
django:uwsgi: started
simulate:simulate_nbp: started

supervisor> exit
```

If you are planning to run the test cruise definition in ``test/NBP1406/NBP1406_cruise.yaml`` then you should also start the process that creates the simulated serial ports that it's configured for:

```
    supervisor> start simulate:simulate_nbp
```

## Manually running scripts

In addition to controlling the scripts through the ``supervisor`` daemon, all OpenRVDAS scripts can be run
from the command line. To do so, you will need to activate the virtual environment that they were configured to run
under, or some of the Python packages they depend on may not be available.

The OpenRVDAS virtual environment may be activated for a shell by running

```source venv/bin/activate```

from the OpenRVDAS home directory. The primary effect of this activation is to modify the default path searched for binaries
so that invoking ``python`` uses the version at ``venv/bin/python`` rather than the default system path. Once activated,
OpenRVDAS scripts may be run by invoking their location, e.g.:
```
logger/listener/listen.py --udp 6204 --write_file /var/log/udp_6204.txt
```
To deactivate the virtual environment, run the ``deactivate`` command.

OpenRVDAS scripts may be run outside the virtual environment by specifying the path to the executable to be use on the
command line. E.g.

```
venv/bin/python logger/listener/listen.py --udp 6204 --write_file /var/log/udp_6204.txt
```
This latter method is how the servers are configured to run inside the supervisor's config file at
``/etc/supervisor.d/openrvdas.ini`` (Ubuntu: ``/etc/supervisor/conf.d/openrvdas.conf``,
MacOS: ``/usr/local/etc/supervisor.d/openrvdas.ini``).