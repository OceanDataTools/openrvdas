# Sikuliaq-Specific Code

This directory contains information and additional code used to
simulate the data setup and run OpenRVDAS on the Sikuliaq.

## Simulating Sikuliaq Dataflow

On Sikuliaq, each instrument writes NMEA strings to a different UDP
port. The instrument-to-port mappings are listed in this directory in
[skq_ports.txt](skq_ports.txt).

The script
[logger/utils/simulate_network.py](../logger/utils/simulate_network.py)
reads from stored logfiles and feeds lines to the appropriate ports at
intervals that mirror the timestamps of the original data. To simulate
a short run of Sikuliaq data, you can it as follows:

```
    logger/utils/simulate_network.py \
       --config test/nmea/SKQ201822S/network_sim_SKQ201822S.yaml \
       --loop
```

## Running OpenRVDAS

The configuration file `test/nmea/SKQ201822S/SKQ201822S_cruise.yaml`
defines a set of loggers and modes (off, file, db, file/db) for
loggers that read from the UDP ports listed in skq/skq_ports.txt and
write to logfiles and/or an SQL database as specified.

The configuration file was created using the quick-and-dirty script:

```
   test/sikuliaq/create_skq_config.py \
     < test/sikuliaq/skq_ports.txt \
     > test/nmea/SKQ201822S/SKQ201822S_cruise.yaml
```

The script generates a configuration with four modes:

  - off - no loggers running
  - file - write logger data to file (currently in /tmp/log/...)
  - db - write logger data to SQL database
  - file/db - write logger data to both file and db

Again, recall that `create_skq_config.py` is a quick and dirty hack for
creating a usable config file (and as such will probably outlive us
all). But please don't expect too much out of it.

### Loading/Running the configuration

If using the command line interface for server/logger_manager.py,
you can specify the desired mode on the command line:

```
    server/logger_manager.py \
      --config test/nmea/SKQ201822S/SKQ201822S_cruise.yaml
      --mode file/db
```

You can also switch between modes by typing the name of the new mode
(or "quit") on the command line while the logger_manager.py is
running.

The configuration file can also be used by the Django gui, as
described in the documentation under django_gui/, where in addition to
selecting between modes, one may manually start/stop/reconfigure
individual loggers as desired.

*Note:* The configuration file specifies Sikuliaq-specific sensor
definitions in test/sikuliaq/sensors.yaml and sensor model definitions
in test/sikuliaq/sensor_models.yaml. Please see [Locations of Message,
Sensor and Sensor Model Definitions in the NMEA Parsing
document](../../docs/nmea_parser.md#locations-of-message-sensor-and-sensor-model-definitions)
for more information on specifying deployment-specific sensor
definitions.

## Running OpenRVDAS Displays

The OpenRVDAS display widgets draw data from a data server. While the
logger\_manager.py script runs a dataserver that feeds off of values
written to the database, the currently recommended approach is to rely
on the standalone
[network_data_server.py](../server/network_data_server.py) script.

To run the script, you will need to tell it what ports to listen to
for NMEA data strings, and where to look for any non-standard sensor
and sensor model definitions. In the case of Sikuliaq, the invocation
would be:

```
server/network_data_server.py --websocket :8766 \
  --read_network :53100,:53104,:53105,:53106,:53107,:53108,:53110,:53111,:53112,:53114,:53116,:53117,:53119,:53121,:53122,:53123,:53124,:53125,:53126,:53127,:53128,:53129,:53130,:53131,:53134,:53135,:54000,:54001,:54109,:54124,:54130,:54131,:55005,:55006,:55007,:58989 \
  --parse_nmea_sensor_path test/sikuliaq/sensors.yaml \
  --parse_nmea_sensor_model_path test/sikuliaq/sensor_models.yaml
``` 

Once the data server is running, you need to make sure the widgets are
looking for it in the right place. They will look for a server
definition in the variable ```WEBSOCKET_DATA_SERVER```, defined in the file
[widgets/static/js/widgets/settings.js](../widgets/static/js/widgets/settings.js).

You will have copied this file over from [widgets/static/js/widgets/settings.js.dist](../widgets/static/js/widgets/settings.js.dist) during installation. To complicate things, if you used the build installation script, it executed Django's "collectstatic" command, which gathered the static files from all the project subdirectories and copied them to a top-level [static/](../static/) directory. Check there, too.

Regardless of its location, you'll want the definition of
```WEBSOCKET_DATA_SERVER``` in settings.py to refer to the hostname
and port that you've used for your ```server/network_data_server.py```
call.

Once you've verified that the server name and port match, you'll need
to make sure that you have something running that can serve the static
widget pages. If you've installed OpenRVDAS as a service, it should
already be running (you can tell if going to
```http://servername:8000``` brings you to the logger management page).

If you don't have OpenRVDAS installed as a service, you can still run
the Django test server with:

```
    ./manage.py runserver localhost:800
```

in which case, you'll want ```WEBSOCKET_DATA_SERVER =
'localhost:8000'``` in ```settings.py```.

At that point you should be able to display (simulated) incoming data
by visiting

[http://localhost:8000/static/widgets/skq_bridge.html](http://localhost:8000/static/widgets/skq_bridge.html)
