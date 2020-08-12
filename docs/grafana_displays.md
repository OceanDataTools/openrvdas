# Grafana/InfluxDB-based Displays with OpenRVDAS
© 2020 David Pablo Cohn - DRAFT 2020-08-12

## Table of Contents

* [Overview](#overview)
* [Installation](#installation)
   * [InfluxDB](#influxdb)
   * [Grafana](#grafana)
   * [Telegraf](#telegraf)
* [Configuration](#configuration)
   * [InfluxDB](#influxdb-1)
   * [Grafana](#grafana-1)
   * [Telegraf](#telegraf-1)
* [Running InfluxDB, Grafana and Telegraf as services](#running-influxdb-grafana-and-telegraf-as-services)
* [Creating Grafana Dashboards](#creating-grafana-dashboards)

## Overview

InfluxDB is a widely-used open source time series database. Grafana is
an open source visualization package. Used together, the two allow
drag-and-drop creation of sophisticated data displays that meet and
exceed the power of OpenRVDAS display tools. We strongly encourage
OpenRVDAS users to focus their efforts toward creating data displays
on the use of Grafana and InfluxDB. Telegraf is an additional package
that can collect system variables such as disk and memory usage and
feed them to InfluxDB. This document describes how to install and
configure InfluxDB, Grafana and Telegraf, how to create cruise
definitions that feed data into them, and the rudiments of how to
create displays that make use of the resulting data.

These instructions describe the process for InfluxDB 2.0, Grafana 7.1
and Telegraf 1.15.

## Installation

The versions of InfluxDB and Grafana that come with CentOS/Red Hat 7
and Ubuntu 18 are somewhat out of date, so we recommend manual
installation of more current versions.

### InfluxDB

You can install and configure InfluxDB as part of the OpenRVDAS
installation script. If you have not done so, you can
install/configure it manually, as below.

```
INFLUXDB_RELEASE=influxdb_2.0.0-beta.16_linux_amd64  # CentOS/Red Hat/Ubuntu
#INFLUXDB_RELEASE=influxdb_2.0.0-beta.16_darwin_amd64  # MacOS

INFLUXDB_URL=dl.influxdata.com/influxdb/releases

cd /tmp
wget http://$INFLUXDB_URL/${INFLUXDB_RELEASE}.tar.gz
tar zxf ${INFLUXDB_RELEASE}.tar.gz
sudo cp ${INFLUXDB_RELEASE}/influx ${INFLUXDB_RELEASE}/influxd /usr/local/bin
```

### Grafana

For Grafana, please follow the instructions on the Grafana download page at [https://grafana.com/grafana/download](https://grafana.com/grafana/download)

Then install two plug-ins we'll want access to:

```
sudo grafana-cli plugins install grafana-influxdb-flux-datasource
sudo grafana-cli plugins install briangann-gauge-panel
​
sudo chown -R grafana /var/lib/grafana/plugins/
sudo chgrp -R grafana /var/lib/grafana/plugins/
```

### Telegraf

```
# CentOS/Red Hat
wget https://dl.influxdata.com/telegraf/releases/telegraf-1.15.2-1.x86_64.rpm
sudo yum localinstall telegraf-1.15.2-1.x86_64.rpm

# Ubuntu
wget https://dl.influxdata.com/telegraf/releases/telegraf_1.15.2-1_amd64.deb
sudo dpkg -i telegraf_1.15.2-1_amd64.deb

# MacOS
brew update
brew install telegraf
brew update telegraf
```

## Configuration

### InfluxDB

* Start a copy of InfluxDB in one window

  ```
  /usr/local/bin/influxd --reporting-disabled
  ```

* Run the setup script in a separate terminal:

  ```
  /usr/local/bin/influx setup
  ```

  We use 'rvdas' when prompted for a user name, 'openrvdas' as the
  organization and 'openrvdas' as the primary bucket.
  
Note that If you are running MacOS Catalina, prior to continuing,
please follow these steps to manually authorize the InfluxDB binaries:

1. Attempt to run /usr/local/bin/influxd from a terminal window.
2. If it balks, open System Preferences and click "Security & Privacy."
3. Under the General tab, there is a message about influxd being
   blocked. Click Open Anyway.
4. Repeat this with /usr/local/bin/influx


### Grafana

Grafana is connected to InfluxDB by adding InfluxDB as a Grafana data
source. To do that, Grafana needs an AUTH_TOKEN from InfluxDB. When
you ran ``influx setup``, the script told you where it was storing its
configuration details (probably in ``/root/.influxdbv2/configs``); you
can find the 'token' string there, or retrieve it via a browser as follows.

* Start up the InfluxDB server again if you've stopped it since the
  previous section

  ```
  /usr/local/bin/influxd --reporting-disabled
  ```

* Start Grafana using systemctl/brew services:

  ```
  # CentOS/Ubuntu
  systemctl start grafana-server

  # MacOS
  brew services start grafana-server
  ```

* Point a browser window ``<machine name>:9999``; log into InfluxDB using
  the username and password you set in the previous step.

* Select the "Load Data" menu on the far left (shaped like an
  old-fashioned disc stack); select "Tokens", then select the
  highlighted-in-blue "<username>'s Token" and "Copy to Clipboard"

* Point your browser to the Grafana server you started at ``<machine
  name>:3000``. You will be prompted to log in. The initial username
  will be admin, password will be: admin. You will be prompted to
  change it. You can change passwords and invite/add more users by
  selecting the gear (settings) icon in the left panel.

* Select the "gear" icon on the far left menu, then "Data sources" and
  "Add data source". Select “Flux (InfluxDB) [BETA]”. Set

  * Default data source as true
  * URL: ``http://machine name>:9999`` # machine where InfluxDB is running
  * Organization: openrvdas
  * Token: Paste this in from your browser clipboard

* Select "Save & Test"

NOTE: If you reinstall InfluxDB, e.g. by re-running the OpenRVDAS
installation script, the InfluxDB AUTH_TOKEN will change, and you will
need to supply the new one to Grafana and Telegraf.

### Telegraf

When Telegraf was installed, it should have created a configuration
file in ``/etc/telegraf/telegraf.conf`` (or
``/usr/local/etc/telegraf/telegraf.conf`` under MacOS). You will need
to edit this file.

1. Comment out the line ``[[outputs.influxdb]]` by adding a "#" to the
   beginning.

1. Uncomment the line ``[[outputs.influxdb_v2]]``; in the section
   below, uncomment the following lines and set their values as follows

    * urls = ["http://127.0.0.1:9999"] 
    * token = "_copy token here_"
    * organization = "openrvdas"
    * bucket = "_monitoring"

The 127.0.0.1:9999 URL assumes that you're running Grafana on the same
machine as InfluxDB. It does not need to be, nor does InfluxDB need to
be running on the same machine as OpenRVDAS. In fact, in production,
it is recommended that InfluxDB run on a separate machine so as to let
the OpenRVDAS machine do nothing but log.

## Running InfluxDB, Grafana and Telegraf as services

Grafana and Telegraf may be started as system services using systemctl
(or `brew services` on MacOS):

```
systemctl start grafana
systemctl start telegraf

brew services start grafana  # MacOS
brew services start telegraf
```

To have them start at machine boot, run

```
systemctl enable grafana
systemctl enable telegraf

brew services enable grafana  # MacOS
brew services enable telegraf
```

InfluxDB requires a bit more work to run as a service. If you
installed InfluxDB as part of the OpenRVDAS installation script, then
it will have an entry in the supervisord configuration file and you
can start it with:

```
supervisorctl start influxdb
```

Otherwise you will need to start it manually:

```
/usr/local/bin/influxd --reporting-disabled
```

## Writing data to InfluxDB

If installation of InfluxDB was selected when the OpenRVDAS
installation script was run, the relevant variables should already be set in ``database/settings.py``; otherwise you will need to edit the file to manually add them:

```
################################################################################
# InfluxDB settings
INFLUXDB_URL = 'http://localhost:9999'
INFLUXDB_ORG = 'openrvdas'
INFLUXDB_AUTH_TOKEN = '4_e-eyx0h8i0UzVkC5jlRy6s4LQM8UXgJAE5xT2a7izbH2_PwyxKY--lQ7FTGvKj5rh9vg04MeksHUL017SNwQ=='  # your InfluxDB token here
```

Once this is set, you should be able to specify and InfluxDBWriter in
your logger configurations, and the data will get to where it needs to
go. Much like a CachedDataWriter, the InfluxDBWriter expects either a
DASRecord or a dict containing 'timestamp' and 'fields' dicts:

```
  gyr1->net:
    name: gyr1->net
    readers:                    # Read from serial port
      class: SerialReader
      kwargs:
        baudrate: 4800
        port: /tmp/tty_gyr1
    transforms:                 # Add timestamp and logger label
    - class: TimestampTransform
    - class: PrefixTransform
      kwargs:
        prefix: gyr1
    - class: ParseTransform     # Parse into a DASRecord
      kwargs:
        metadata_interval: 10
        definition_path: local/usap/nbp/devices/nbp_devices.yaml
    writers:
    - class: CachedDataWriter   # Send to Cached Data Server
      kwargs:
        data_server: localhost:8766
    - class: InfluxDBWriter     # Send to InfluxDB
      kwargs:
        bucket_name: openrvdas
        measurement_name: gyr1
```

## Creating Grafana Dashboards

* To start a new dashboard, select the “+” at the left menu, then
  select “Dashboards.” Select the “Add new panel” button (widgets are
  called “panels” here).

* You’ll be able to select a “Visualization” to choose between graphs,
  numerical stats, dials, etc. 360 degree dials are created using a
  “D3 Gauge” which was the “briangann-gauge-panel” we loaded above
  from Grafana labs.

* To get the data into the visualization, you’ll need to create a
  query in the Flux query language. I haven’t attempted to learn
  it. Instead, I generate the query using the InfluxDB server:

  * Open a browser on the machine serving InfluxDB, e.g
    http://nbp-odas-t:9999

  * Select “Data Explorer (the zigzag) from the left panel. This will
    show you what fields are available. Select the sensors and field
    names you want, along with any modifications (mean, median, skew,
    etc). You can also select graph type (above to left) but that
    won’t affect the data query.

  * Hit “Submit” (over on right) to check that you’ve got the data you
    want. Don’t forget to set the refresh rate and window size so that
    you can confirm you’re getting real data.

  * Once you’ve got the data you want showing up in the Data Explorer,
    select “Script Editor” (next to the “Submit” button”), and you’ll
    be shown the Flux query used to retrieve the data. Copy that and
    paste it into the query box in your Grafana panel editor (bottom,
    to the left, under “A”).

* Hit “Save” and “Apply”

* Panels may be dragged around and resized. Don’t forget to hit “Save”
  (the floppy icon) prior to leaving your dashboard page.

Note: If things behave badly after installing a plug-in, check the
file permissions insides /var/lib/grafana/plugins - it seems that they
sometimes get wonked by installations.

![Sample Grafana Dashboard](images/grafana_dashboard.png)
