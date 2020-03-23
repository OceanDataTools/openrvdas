# Configuring InfluxDB for Use with OpenRVDAS

[InfluxDB](https://v2.docs.influxdata.com/v2.0/) is a powerful time
series database that supports fast retrieval and display operations
using [Grafana](https://grafana.com/grafana/).

An InfluxDBWriter can feed InfluxDB from OpenRVDAS, but InfluxDB is
not installed of configured by the default OpenRVDAS installation
scripts. This file describes how to get/install/configure InfluxDB to
work with OpenRVDAS.


## Get InfluxDB

Note that the paths described below will vary depending on your system.

* Download the appropriate binary (Linux/MacOS) from the links at
[https://v2.docs.influxdata.com/v2.0/get-started/](https://v2.docs.influxdata.com/v2.0/get-started/).

  ```
  cd /tmp
  wget https://dl.influxdata.com/influxdb/releases/influxdb_2.0.0-beta.1_linux_amd64.tar.gz
  ```

* Uncompress the downloaded archive from wherever it is stored and copy its contents into this directory.

  ```
  tar xvfz influxdb_2.0.0-beta.1_linux_amd64.tar.gz
  cp -r influxdb_2.0.0-beta.1_linux_amd64 /opt/openrvdas/database/influxdb/bin
  ```

## Configure InfluxDB and set up credentials

* Start the influxdb server running.

  ```
  /opt/openrvdas/database/influxdb/bin/influxd --reporting-disabled
  ```

  Note that if you're running on MacOS Catalina, the OS will flag the script as untrusted the first time you run it, and you will have to go to __System Preferences > Security & Privacy__ to select "Allow influxd", then run it again.

* Set up the InfluxDB user credentials. In a separate terminal, run:

  ```
  /opt/openrvdas/database/influxdb/bin/influx setup \
    --username rvdas --password rvdasrvdas \
    --org openrvdas --bucket openrvdas \
    --force
  ```

  As with influxd, on MacOS Catalina, you will need to authorize the script the first time, then re-run it.

## Copy the credentials into place.

*  When ``setup`` finishes running, it will tell you where it has stored the token it generated for you:

  ```
  Your token has been stored in /Users/rvdas/.influxdbv2/credentials.
  User    Organization    Bucket
  rvdas    openrvdas    openrvdas
  ```

  Copy the ``settings.py.dist`` file in this directory over to ``settings.py``, and edit the definitions of ``INFLUXDB_ORG`` and ``INFLUXDB_AUTH_TOKEN`` to match the organization specified during setup, and the token string stored in the credentials file:

  ```
  cp settings.py.dist settings.py

  vi settings.py

  # Make changes here so that last two lines of settings.py look as follows
  # except that the AUTH_TOKEN is the one from your newly-generated
  # credentials file.

  INFLUXDB_ORG = 'openrvdas'
  INFLUXDB_AUTH_TOKEN = 'MKRK2bRwy1-RSzvXOeC85cW2yQrhVHwX5oeFhJ1UBd3zjz39Zqg97WRdr8u4RkSBiyOwX2ck4zixMnOml7SAoQ=='
  ```

## Install the InfluxDB Python client

Use the venv path version of pip to make sure the client is installed for the correct version of Python.

```
cd /opt/openrvdas
venv/bin/pip install influxdb_client
```

## Using InfluxDB

At this point, an instance of ``InfluxDBWriter`` should be able to
write to the database. You should also be able to point a browser at
the default InfluxDB server port (http://localhost:9999) and log in
using the username and password specified during setup
(e.g. rvdas/rvdasrvdas). by navigating to the "Data Explorer" (the
graph icon on the left of the page) you should be able to select and
plot values that are being written to the database

To use InfluxDB in production, you will want to run it using
supervisor instead of from a terminal. Locate the
``supervisor.d/openrvdas.ini`` file produced by the OpenRVDAS
installation script (in CentOS it should be in
``/etc/supervisor/conf.d/openrvdas.conf``, in Ubuntu in
``/etc/supervisord.d/openrvdas.ini``, and in MacOS in
``/usr/local/etc/supervisor.d/openrvdas.ini``). Find the program block that describes the command for running InfluxDB and uncomment it:

```
; Uncomment the following command block if you've installed InfluxDB
; and want it to run as a service.
[program:influxdb]
command=database/influxdb/bin/influxd --reporting-disabled
directory=/opt/openrvdas
autostart=false
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/influxdb.err.log
stdout_logfile=/var/log/openrvdas/influxdb.out.log
user=rvdas
```

If ``autostart=true`` the service will run when the system boots. If
autostart is false, you will need to manually start/stop it by running

```
> supervisorctl start influxdb
```