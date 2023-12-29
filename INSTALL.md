# OpenRVDAS Installation Guide
At the time of this writing OpenRVDAS has been built and tested against MacOS X, CentOS 7-9, Rocky 8-9, Ubuntu 18-23
and Raspbian operating systems. It may be possible to build against other Linux-based operating systems, and guides
will be added here as they are verified and documented.

You will need to be able to run the ``sudo`` command. To begin installation, grab the script from github and run from the command line:
```
OPENRVDAS_REPO=raw.githubusercontent.com/oceandatatools/openrvdas
BRANCH=master
curl -O -L https://$OPENRVDAS_REPO/$BRANCH/utils/install_openrvdas.sh
chmod +x install_openrvdas.sh
sudo ./install_openrvdas.sh
```
selecting ``master``, ``dev`` or other branch of the repo if your project has one.

On MacOS, it should be run as a user that has sudo permissions (the script will prompt several times
for the sudo password when needed):

_The script will ask a lot of questions and provide default answers in parens that will be filled in if you hit "return"; without any other input:_

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

_Script will next ask about database options. If this is the first time you've run the script and MySQL/MariaDB has not already been installed, the current root database password will be empty:_

```
Database password to use for rvdas? (rvdas)
Current database password for root? (if one exists - hit return if not)
New database password for root? () **rvdas**

############################################################################
The OpenRVDAS server can be configured to start on boot. Otherwise
you will need to either run it manually from a terminal (by running
server/logger_manager.py from the openrvdas base directory) or
start as a service (service openrvdas start).

Do you wish to start the OpenRVDAS server on boot? **y**
```

The script will run a while and, if all has gone well, wish you "Happy logging" when it has completed.

## Post-Installation

The installation should allow you to connect via http to the server at the name you specified at the start of the script (e.g. ``lmg-dast-s1-t``). If you want to connect using any other names, e.g. the fully-qualified domain name ``lmg-dast-s1-t.lmg.usap.gov``, you'll need to add it to the Django server settings file in ``django_gui/settings.py``:

```
ALLOWED_HOSTS = [HOSTNAME, 'localhost', HOSTNAME + '.lmg.usap.gov']
```
If you make this change, you will want to restart several services:

```
supervisorctl restart web:*
```

If you wish to use InfluxDB and Grafana to create dashboards and display data, you
will need to run the installation script in `utils/install_influxdb.sh`. Please
see and follow the instructions in [Grafana/InfluxDB-based Displays](docs/grafana_displays.md).

## Starting and Stopping Servers

In addition to the NGINX webserver (and its Python helper interface UWSGI), OpenRVDAS relies on two servers: ``logger_manager.py`` and ``cached_data_server.py`` (see [Controlling Loggers](docs/controlling_loggers.md) for details). 

The easiest way to manage these servers is via the supervisord package that is installed by the installation script. If you answered 'yes' when asked whether OpenRVDAS should start automatically on boot up, supervisord will start them for you; if you answered 'no', the supervisord configurations will have still be created, but you will need to manually tell supervisord to start/stop them.

You can do this two ways, either via the local webserver at [http://openrvdas:9001](http://openrvdas:9001) (assuming your machine is named 'openrvdas') or via the command line ``supervisorctl`` tool:

```
  rvdas@openrvdas:~> supervisorctl
  openrvdas:cached_data_server     STOPPED   Nov 10 08:32 PM
  openrvdas:logger_manager         STOPPED   Nov 10 08:32 PM
  simulate:simulate_nbp            STOPPED   Nov 10 08:32 PM
  web:nginx                        STOPPED   Nov 10 08:32 PM
  web:uwsgi                        STOPPED   Nov 10 08:32 PM

  supervisor>  start openrvdas:*
  openrvdas:logger_manager: started
  openrvdas:cached_data_server: started

  supervisor> status
  openrvdas:cached_data_server     RUNNING   pid 4132, uptime 0:00:28
  openrvdas:logger_manager         RUNNING   pid 4131, uptime 0:00:28
  simulate:simulate_nbp            STOPPED   Nov 10 08:32 PM
  web:nginx                        STOPPED   Nov 10 08:32 PM
  web:uwsgi                        STOPPED   Nov 10 08:32 PM

  supervisor> exit
```

If you are planning to run the test cruise definition in ``test/NBP1406/NBP1406_cruise.yaml`` then you should also start the process that creates the simulated serial ports that it's configured for:

```
    supervisor> start simulate:simulate_nbp
```

You may also use broader acting commands with supervisorctl, such as
``start all``, ``stop all`` and ``restart all``.

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