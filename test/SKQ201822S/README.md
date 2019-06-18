# Sikuliaq-Specific Code

This directory contains information and additional code used to
simulate the data setup and run OpenRVDAS on the Sikuliaq.

## Simulating Sikuliaq Dataflow

On Sikuliaq, each instrument writes NMEA strings to a different UDP
port. The instrument-to-port mappings are listed in
``test/SKQ201822S/CREATE_SKQ_CRUISE/skq_ports.txt``.

This dataflow can be simulated using the script
[logger/utils/simulate_network.py](../../logger/utils/simulate_network.py). Given a configuration file that encodes the above mapping, it
reads from stored logfiles and feeds lines to the appropriate ports at
intervals that mirror the timestamps of the original data. To simulate
a short run of Sikuliaq data, you can it as follows:

```
    logger/utils/simulate_network.py \
       --config test/SKQ201822S/network_sim_SKQ201822S.yaml \
       --loop
```

(The script that created the above config file is at
``test/SKQ201822S/CREATE_SKQ_CRUISE/create_skq_sim.py`` - see its
headers for details on running it.)

## Running OpenRVDAS

The configuration file `test/SKQ201822S/SKQ201822S_cruise.yaml`
defines a set of loggers and modes (off, file, db, file/db) for
loggers that read from the UDP ports listed in skq/skq_ports.txt and
write to logfiles and/or an SQL database as specified.

The configuration file was created using another quick-and-dirty script:

```
   test/SKQ201822S/CREATE_SKQ_CRUISE/create_skq_config.py \
     < test/SKQ201822S/CREATE_SKQ_CRUISE/skq_ports.txt \
     > test/SKQ201822S/SKQ201822S_cruise.yaml
```

The script generates a configuration with four modes:

  - off - no loggers running
  - file - write logger data to file (currently in /tmp/log/...)
  - db - write logger data to SQL database
  - file/db - write logger data to both file and db

Again, recall that `create_skq_config.py` is a quick and dirty hack for
creating a usable config file (and as such will probably outlive us
all). But please don't expect too much out of it.

### Manually loading/running the configuration

If using the command line interface for server/logger_manager.py,
you can specify the desired mode on the command line:

```
    server/logger_manager.py \
      --config test/SKQ201822S/SKQ201822S_cruise.yaml \
      --mode file/db
```

You can also switch between modes by typing

```
  set_active_mode file
```

or whatever your desired mode is (type 'help' on the command line to get a list of all available commands).

The configuration file can also be used by the Django GUI, as
described in the documentation under django_gui/, where in addition to
selecting between modes, one may manually start/stop/reconfigure
individual loggers as desired.

*Note:* The configuration file specifies Sikuliaq-specific sensor
definitions in [test/SKQ201822S/CREATE\_SKQ\_CRUISE/sensors.yaml](SKQ201822S/CREATE_SKQ_CRUISE/sensors.yaml) and sensor model definitions
in [test/SKQ201822S/CREATE\_SKQ\_CRUISE/sensor_models.yaml](SKQ201822S/CREATE_SKQ_CRUISE/sensor_models.yaml). Please see [Locations of Message,
Sensor and Sensor Model Definitions in the NMEA Parsing
document](../../docs/nmea_parser.md#locations-of-message-sensor-and-sensor-model-definitions)
for more information on specifying deployment-specific sensor
definitions.

*Another Note:* The configuration file uses "old style" NMEA parsing, with sensor and sensor_model files. We strongly recommend that any new configurations that are created use the more general RecordParser described in the [Record Parsing document](../../docs/parsing).

### Loading/Running the configuration via the Django GUI

If you've used one of the standard build scripts to create you
OpenRVDAS installation, you will have the Django-based GUI
available. Assuming the OpenRVDAS service is running (```service
openrvdas start```), you should be able to point a browser at

   [http://localhost:8000](http://localhost:8000)

and see the default cruise management page. After logging in, you
should be able to select the 'Load configuration file' button at the
bottom, select a file and load it using the 'Load' button. Please see
the [Django Web Interface](../../docs/django_interface.md) document
for more information on using the web interface.

## Running OpenRVDAS Displays

### Running a data server

The OpenRVDAS display widgets draw data from a data server. If you
have run one of the standard installation scripts, your logger_manager
service is configured to automatically start up a CachedDataServer on
startup (see the script in ``/root/scripts/start_openrvdas.sh`` to
check whether ``START_DATA_SERVER`` is commented out).

If you are running a logger_manager manually, you may direct it to start a CachedDataServer with the addition of a flag:

```
    server/logger_manager.py \
      --config test/nmea/SKQ201822S/SKQ201822S_cruise.yaml \
      --mode file/db \
      --start_data_server
```
By default, the CachedDataServer will listen for UDP broadcasts on
port 6225 and accept websocket connections on port 8766, though both
of these may be altered with command line flags (use the ``--help``
flag for details).

### Displaying data

If you have installed via one of the standard scripts, NGINX will be
running as a web service, and you should be able to visit

   [http://localhost:8000](http://localhost:8000)

to see and select which loggers are running. Otherwise, you can run

```
  ./manage.py runserver localhost:8000
```
to achieve the same effect using Django's test server.

The Django configuration will serve a simple dynamic data widget at

   [http://localhost:8000/widget/](http://localhost:8000/widget/)

Going to that page and appending a comma-separated list of field names should display a table of the latest values for those fields, e.g.:

   [http://localhost:8000/widget/wind\_mast\_port\_speed,wind_mast\_port\_direction](http://localhost:8000/widget/wind_mast_port_speed,wind_mast_port_direction)

There is also a more complex widget display page to simulate the Sikuliaq's "Bridge data" page at

   [http://localhost:8000/static/widgets/skq\_bridge.html](http://localhost:8000/static/widgets/skq_bridge.html)

This page was constructed using component display widgets as described in the ["Widget Content"](../docs/display_widgets.md#widget-content) section of the [Display Widgets document](docs/display_widgets.md). Please see that document for information on building/customizing your own display widgets.
