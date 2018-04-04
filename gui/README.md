# OpenRVDAS Django GUI (DRAFT)

## Overview

Please see the [README.md file in the parent directory](../README.md)
for an introduction to the OpenRVDAS system. This document discusses
specifically a Django-based GUI for interacting with the system.

Django (<https://www.djangoproject.com/>) is a high-level web
framework written in/for Python. It is not intended to be *the* GUI
framework for OpenRVDAS, just one framework with which OpenRVDAS
works.

The current code in this directory represents a very preliminary GUI
that will likely change substantially both in look-and-feel and
underlying implementation. It is presented here a proof of concept
from which to identify shortcomings in performance, functionality and
ease of use.

## Installation

If you have already installed the files needed to run the core
OpenRVDAS code, as described in [the parent directory
INSTALL.md](../INSTALL.md), there are only a couple more steps needed
to run the GUI:

1. Install Django and websockets (future implementations may use
Django's "channels" functionality rather than websockets):
```
  pip3 install websockets
  pip3 install Django==2.0
```

## Running

This section describes running the GUI using the simplified Django
test server and the default SQLite database. Actual deployments will
likely require more robust services, such as Apache and MySQL or
MariaDB.

1. Set up the default Django database models (uses SQLite, as
configured in gui/settings.py):
```
  python3 manage.py makemigrations gui
  python3 manage.py migrate
  python3 manage.py createsuperuser --email rvdas@somerandom.com --username rvdas
```
2. Generate a full cruise configuration for the server to use. To use
the sample cruise definition for running on test data, run:
```
  python3 logger/utils/build_config.py --config test/configs/sample_cruise.json > cruise.json
```
3. Start the test server
```
  python3 manage.py runserver localhost:8000
```
4. In a browser window, visit ```http://localhost:8000```
5. In a separate window, run gui/run_servers.py
```
  python3 gui/run_servers.py
```
Note that run_servers.py will need access to port 8765 (by default - you can change this in gui/settings.py). On CentOS, add this via:
```
sudo firewall-cmd --permanent --add-port=8765/tcp
sudo firewall-cmd --reload
```

6. The sample cruise configuration relies on simulated serial ports
serving data stored in the test/ directory. To set up the simulated
ports, run
```
  python3 logger/utils/simulate_serial.py --config test/serial_sim.json 
```

At this point in the browser window, you should see an indication that
no configuration is loaded, along with a prompt to log in. Log in
using the rvdas account you created.

Select "Load configuration file" to select and load the
```cruise.json``` configuration file you created in Step 2.

The GUI window should now update to show a set of loggers,
configurations and mode selector in mode "off". Select the mode
"underway" (it will turn yellow), then hit "change mode" to
commit. The LoggerServer will select the logger configurations
appropriate for the selected mode and run them.

You can manually select configurations on a logger-by-logger basis by
selecting the configuration button for that logger and using the
resulting pull-down menu. If a logger is not in the default
configuration for the current mode, its configuration button will be
yellow.

The sample configurations use UDP broadcasts to port 6224 for network
writes and subdirectories under /tmp/log/NBP1700/ for file writes. You
can run a listener on the port using
```
  python3 logger/listener/listen.py --network :6224 --write_file -
```
to listen to the appropriate port, or
```
  tail -f /tmp/log/NBP1700/*/*/*
```
to watch logfiles being written.

Note also that you can still observe the state of the system if you
are not logged in (e.g. as ```rvdas```), but you will be unable to
select or change any configurations.

The "Manage Servers" button will open a page from which (when it is
working), you will be able to stop and restart logger and status
servers. You can also use links on that page to open other pages that
monitor the messages emitted by the individual servers.

### Widgets

A very rudimentary display widget has been implemented in
```
http://localhost:8000/widget
```
It draws its data from records written to the database, so will only
display new data when the relevant loggers are writing to the database
(in the sample configuration, this happens in underway mode, or if you
manually select a net/file/db configuration for an individual logger).

To use it, append the widget path name with a comma-separated list of
Fields you wish to monitor, e.g.
```
http://localhost:8000/widget/S330Roll,S330Pitch
```
The S330Roll and S330Pitch fields are produced by the s330 logger,
so select and enable the s330 -> net/file/db configuration. If
all has gone well, the widget values should begin to update.

## Next Steps

1. Allow servers to be started/stopped from the web UI. This would
probably entail making run_servers.py an always-running service and
have the management page control it by storing desired server states
in the Django ServerStates table.

2. The current UI is...rudimentary. It would be nice to have someone
who understands both UI and web design to have a go at a V2.

## Contributing

Please contact David Pablo Cohn (*david dot cohn at gmail dot com*) -
to discuss opportunities for participating in code development.

## License

This code is made available under the MIT license:

Copyright (c) 2017 David Pablo Cohn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Additional Licenses
