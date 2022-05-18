#!/bin/bash -e

# OpenRVDAS is available as open source under the MIT License at
#   https:/github.com/oceandatatools/openrvdas
#
# This script installs and configures InfluxDB, Grafana (and
# optionally Telegraf) and creates a supervisord file that allows them
# to be started/stopped by supervisorctl. It should be run as the user
# who will be running OpenRVDAS (e.g. 'rvdas'):
#
#     sudo rvdas utils/install_influxdb.sh
#
# The script has been designed to be idempotent, that is, if can be
# run over again with no ill effects.
#
# Once installed, you should be able to start/stop/disable the
# relevant services using supervisorctl. If you have selected "Run
# (InfluxDB/Grafana/Telegraf) on boot," those services should start up
# as soon as supervisord does. If you have selected them to not start
# on boot, you can start/stop/restart them manually using
# supervisorctl:
#
# > supervisorctl status
# influx:grafana                   STOPPED   Sep 13 06:22 AM
# influx:influxdb                  STOPPED   Sep 13 06:22 AM
# influx:telegraf                  STOPPED   Sep 13 06:22 AM
#
# > supervisorctl start influx:influxdb
# influx:influxdb: started
#
# > supervisorctl start influx:*
# influx:grafana: started
# influx:telegraf: started
#
# When running, you should be able to reach the relevant servers at:
#  - influxdb:       localhost:9999
#  - grafana-server: localhost:3000
#
# This script is somewhat rudimentary and has not been extensively
# tested. If it fails on some part of the installation, there is no
# guarantee that fixing the specific issue and simply re-running will
# produce the desired result.  Bug reports, and even better, bug
# fixes, will be greatly appreciated.
#
# ***************************************
# NOTE: If you are running MacOS Catalina
# ***************************************
#
# MacOS Catalina requires downloaded binaries to be signed by
# registered Apple developers. Currently, when you first attempt to
# run influxd or influx, macOS will prevent it from running.
#
# If you are running MacOS Catalina, prior to continuing, please
# follow these steps to manually authorize the InfluxDB binaries:
#
# 1. Attempt to run /usr/local/bin/influx in a separate window.
# 2. Open System Preferences and click "Security & Privacy."
# 3. Under the General tab, there is a message about influx being
# "   blocked. Click Open Anyway."
# 4. Repeat this with /usr/local/bin/influxd
#

PREFERENCES_FILE='.install_influxdb_preferences'

# Defaults that will be overwritten by the preferences file, if it
# exists.
DEFAULT_INSTALL_ROOT=/opt
#DEFAULT_HTTP_PROXY=proxy.lmg.usap.gov:3128 #$HTTP_PROXY
DEFAULT_HTTP_PROXY=$http_proxy

DEFAULT_INFLUXDB_USER=rvdas
DEFAULT_INFLUXDB_PASSWORD=rvdasrvdas

DEFAULT_INSTALL_INFLUXDB=yes
DEFAULT_INSTALL_GRAFANA=yes
DEFAULT_INSTALL_TELEGRAF=yes

DEFAULT_RUN_INFLUXDB=no
DEFAULT_RUN_GRAFANA=no
DEFAULT_RUN_TELEGRAF=no

# Organization to be used by OpenRVDAS and Telegraf when writing to InfluxDB
ORGANIZATION=openrvdas

# Bucket Telegraf should write its data to
TELEGRAF_BUCKET=_monitoring

###########################################################################
###########################################################################
function exit_gracefully {
    echo Exiting.

    # Try deactivating virtual environment, if it's active
    if [ -n "$INSTALL_ROOT" ];then
        deactivate
    fi
    return -1 2> /dev/null || exit -1  # exit correctly if sourced/bashed
}

###########################################################################
###########################################################################
function get_os_type {
    if [[ `uname -s` == 'Darwin' ]];then
        OS_TYPE=MacOS
    elif [[ `uname -s` == 'Linux' ]];then
        if [[ ! -z `grep "NAME=\"Ubuntu\"" /etc/os-release` ]] || [[ ! -z `grep "NAME=\"Debian" /etc/os-release` ]] || [[ ! -z `grep "NAME=\"Raspbian" /etc/os-release` ]];then
            OS_TYPE=Ubuntu
        elif [[ ! -z `grep "NAME=\"CentOS Linux\"" /etc/os-release` ]] || [[ ! -z `grep "NAME=\"Red Hat Enterprise Linux Server\"" /etc/os-release` ]] || [[ ! -z `grep "NAME=\"Red Hat Enterprise Linux Workstation\"" /etc/os-release` ]];then
            OS_TYPE=CentOS
        else
            echo Unknown Linux variant!
            exit_gracefully
        fi
    else
        echo Unknown OS type: `uname -s`
        exit_gracefully
    fi
    echo Recognizing OS type as $OS_TYPE
}

###########################################################################
###########################################################################
# Read any pre-saved default variables from file
function set_default_variables {
    # Read in the preferences file, if it exists, to overwrite the defaults.
    if [ -e $PREFERENCES_FILE ]; then
        echo Reading pre-saved defaults from "$PREFERENCES_FILE"
        source $PREFERENCES_FILE
    fi
}

###########################################################################
###########################################################################
# Save defaults in a preferences file for the next time we run.
function save_default_variables {
    cat > $PREFERENCES_FILE <<EOF
# Defaults written by/to be read by utils/install_influxdb.sh

DEFAULT_INSTALL_ROOT=$INSTALL_ROOT  # path where openrvdas is found
#DEFAULT_HTTP_PROXY=proxy.lmg.usap.gov:3128 #$HTTP_PROXY
DEFAULT_HTTP_PROXY=$HTTP_PROXY

DEFAULT_INFLUXDB_PASSWORD=$INFLUXDB_PASSWORD

DEFAULT_INSTALL_INFLUXDB=$INSTALL_INFLUXDB
DEFAULT_INSTALL_GRAFANA=$INSTALL_GRAFANA
DEFAULT_INSTALL_TELEGRAF=$INSTALL_TELEGRAF

DEFAULT_RUN_INFLUXDB=$RUN_INFLUXDB
DEFAULT_RUN_GRAFANA=$RUN_GRAFANA
DEFAULT_RUN_TELEGRAF=$RUN_TELEGRAF
EOF
}

#########################################################################
#########################################################################
# Return a normalized yes/no for a value
yes_no() {
    QUESTION=$1
    DEFAULT_ANSWER=$2

    while true; do
        read -p "$QUESTION ($DEFAULT_ANSWER) " yn
        case $yn in
            [Yy]* )
                YES_NO_RESULT=yes
                break;;
            [Nn]* )
                YES_NO_RESULT=no
                break;;
            "" )
                YES_NO_RESULT=$DEFAULT_ANSWER
                break;;
            * ) echo "Please answer yes or no.";;
        esac
    done
}

###########################################################################
# An ugly, but necessary thing.
function get_influxdb_auth_token {

    CONFIG_FILE=~/.influxdbv2/configs
    if [[ ! -e $CONFIG_FILE ]];then
        echo "No InfluxDB config file found: $CONFIG_FILE; can't extract token"
        return
    fi
    TOKEN_LINE=`grep '^  token = ' $CONFIG_FILE`
    INFLUXDB_AUTH_TOKEN=`echo $TOKEN_LINE | cut -d\" -f2`

    if [[ -z "$INFLUXDB_AUTH_TOKEN" ]];then
        echo Unable to find InfluxDB auth token in config file \"$CONFIG_FILE\"
        exit_gracefully
    else
        echo Retrieved InfluxDB auth token: $INFLUXDB_AUTH_TOKEN
    fi
}

###########################################################################
# Create database/influxdb/settings.py and set up our new token
function fix_database_settings {
    # Make sure we've got an InfluxDB auth token
    get_influxdb_auth_token

    SETTINGS=$INSTALL_ROOT/openrvdas/database/influxdb/settings.py
    cp ${SETTINGS}.dist $SETTINGS

    sed -i -e "s/INFLUXDB_ORG = '.*'/INFLUXDB_ORG = '$ORGANIZATION'/" $SETTINGS
    sed -i -e "s/INFLUXDB_AUTH_TOKEN = '.*'/INFLUXDB_AUTH_TOKEN = '$INFLUXDB_AUTH_TOKEN'/" $SETTINGS

    # If they've run this with an old installation of OpenRVDAS,
    # database/settings.py may have the old/wrong port number for InfluxDB
    sed -i -e "s/INFLUXDB_URL = 'http:\/\/localhost:9999'/INFLUXDB_URL = 'http:\/\/localhost:8086'/" $SETTINGS
}

###########################################################################
###########################################################################
# If we're on RHEL/CentOS and firewalld is running, open the ports we'll
# need to have available.
function open_required_ports {
    if [ $OS_TYPE == 'CentOS' ] && [ `systemctl is-active firewalld` == 'active' ]; then
        echo Opening ports 8086 \(InfluxDB\) and 3000 \(Grafana\)
        sudo firewall-cmd -q --permanent --add-port=9999/tcp > /dev/null  # InfluxDB
        sudo firewall-cmd -q --permanent --add-port=8086/tcp > /dev/null  # InfluxDB
        sudo firewall-cmd -q --permanent --add-port=3000/tcp > /dev/null  # Grafana
        sudo firewall-cmd -q --reload > /dev/null
    fi
}
###########################################################################
###########################################################################
# Install and configure InfluxDB - to be run *after* OpenRVDAS is in place!
function install_influxdb {
    # Expect the following shell variables to be appropriately set:
    # INSTALL_ROOT - where openrvdas/ may be found
    # INFLUXDB_USER - valid userid
    # INFLUXDB_PASSWORD - password to use for InfluxDB

    INFLUXDB_REPO=dl.influxdata.com/influxdb/releases
    INFLUXDB_RELEASE=influxdb2-2.0.8

    echo "#####################################################################"
    echo Installing InfluxDB...

    # Is there already an installation?
    if [ -d ~/.influxdbv2 ];then
        echo
        echo "An installation of InfluxDB appears to already exist. Overwriting"
        echo "will reset any existing tokens and require resetting connections "
        echo "from all Grafana and Telegraf servers."
        yes_no "Overwrite existing installation?" no
        if [ $YES_NO_RESULT == 'no' ];then
            return 0
        fi
    fi

    # If here, we're installing new or overwriting the existing installation.
    # Clear out any old setup directories.
    rm -rf ~/.influxdbv2

    # If we're on MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        INFLUXDB_PACKAGE=${INFLUXDB_RELEASE}-darwin-amd64 # for MacOS
    # If we're on Linux
    elif [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
        INFLUXDB_PACKAGE=${INFLUXDB_RELEASE}-linux-amd64 # for Linux
    else
        echo "ERROR: No InfluxDB binary found for architecture \"`uname -s`\"."
        exit_gracefully
    fi
    INFLUXDB_URL=https://${INFLUXDB_REPO}/${INFLUXDB_PACKAGE}.tar.gz

    # Grab, uncompress and copy into place
    pushd /tmp >> /dev/null
    if [ -e ${INFLUXDB_PACKAGE}.tar.gz ]; then
        echo Already have archive locally: /tmp/${INFLUXDB_PACKAGE}.tar.gz
    else
        echo Fetching binaries
        wget $INFLUXDB_URL
    fi
    if [ -d ${INFLUXDB_PACKAGE} ]; then
        echo Already have uncompressed release locally: /tmp/${INFLUXDB_PACKAGE}
    else
        echo Uncompressing...
        tar xzf ${INFLUXDB_PACKAGE}.tar.gz
    fi
    echo Copying into place...
    sudo cp -f  ${INFLUXDB_PACKAGE}/influx ${INFLUXDB_PACKAGE}/influxd /usr/local/bin
    popd >> /dev/null

    # Run setup
    echo "#################################################################"
    echo Running InfluxDB setup - killing all currently-running instances
    pkill -x influxd || echo No processes killed
    echo Running server in background
    /usr/local/bin/influxd --reporting-disabled > /dev/null &
    echo Sleeping to give server time to start up
    sleep 20  # if script crashes at next step, increase this number a smidge
    echo Running influx setup
    /usr/local/bin/influx setup \
        --username $INFLUXDB_USER --password $INFLUXDB_PASSWORD \
        --org openrvdas --bucket openrvdas --retention 0 --force # > /dev/null
    echo Killing the InfluxDB instance we started
    pkill -x influxd || echo No processes killed

    # Set the values in database/settings.py so that InfluxDBWriter
    # has correct default organization and token.
    fix_database_settings

    # Install the InfluxDB python client
    echo "#################################################################"
    echo Installing Python client
    pip install \
      --trusted-host pypi.org --trusted-host files.pythonhosted.org \
      influxdb_client

    echo Done setting up InfluxDB!
}

###########################################################################
###########################################################################
# Install and configure Grafana - to be run *after* OpenRVDAS is in place!
function install_grafana {
    echo "#####################################################################"
    echo Installing Grafana...
    GRAFANA_RELEASE=grafana-8.1.2
    GRAFANA_REPO=dl.grafana.com/oss/release

    # If we're on MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        GRAFANA_PACKAGE=${GRAFANA_RELEASE}.darwin-amd64 # for MacOS
    # If we're on Linux
    elif [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
        GRAFANA_PACKAGE=${GRAFANA_RELEASE}.linux-amd64 # for Linux
    else
        echo "ERROR: No Grafana binary found for architecture \"`uname -s`\"."
        exit_gracefully
    fi
    GRAFANA_URL=https://${GRAFANA_REPO}/${GRAFANA_PACKAGE}.tar.gz

    # Grab, uncompress and copy into place
    pushd /tmp >> /dev/null
    if [ -e ${GRAFANA_PACKAGE}.tar.gz ]; then
        echo Already have archive locally: /tmp/${GRAFANA_PACKAGE}.tar.gz
    else
        echo Fetching binaries
        wget $GRAFANA_URL
    fi
    if [ -d ${GRAFANA_RELEASE} ]; then
        echo Already have uncompressed release locally: /tmp/${GRAFANA_RELEASE}
    else
        echo Uncompressing...
        tar xzf ${GRAFANA_PACKAGE}.tar.gz
    fi

    echo Copying into place...
    if [ $OS_TYPE == 'MacOS' ]; then
        cp -rf ${GRAFANA_RELEASE} /usr/local/etc/grafana
        ln -fs /usr/local/etc/grafana/bin/grafana-server /usr/local/bin
        ln -fs /usr/local/etc/grafana/bin/grafana-cli /usr/local/bin
    # If we're on Linux
    elif [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
        CURRENT_USER=$USER
        sudo cp -rf ${GRAFANA_RELEASE} /usr/local/etc/grafana
        sudo ln -fs /usr/local/etc/grafana/bin/grafana-server /usr/local/bin
        sudo ln -fs /usr/local/etc/grafana/bin/grafana-cli /usr/local/bin
        sudo chown -R $CURRENT_USER /usr/local/etc/grafana
    fi
    popd >> /dev/null

    grafana-cli --homepath /usr/local/etc/grafana admin reset-admin-password $INFLUXDB_PASSWORD

    PLUGINS_DIR=/usr/local/etc/grafana/data/plugins
    echo Downloading plugins
    /usr/local/bin/grafana-cli --pluginsDir $PLUGINS_DIR plugins install grafana-influxdb-flux-datasource
    /usr/local/bin/grafana-cli --pluginsDir $PLUGINS_DIR plugins install briangann-gauge-panel

    echo Done setting up Grafana!
}

###########################################################################
# Install and configure Telegraf - to be run *after* OpenRVDAS is in place!
function install_telegraf {
    echo "#####################################################################"
    echo Installing Telegraf...
    TELEGRAF_RELEASE=telegraf-1.19.3
    TELEGRAF_REPO=dl.influxdata.com/telegraf/releases

    # NOTE: in 1.13.3, the tgz file uncompresses to a directory that
    # doesn't include the release number, so just 'telegraf'
    TELEGRAF_UNCOMPRESSED=$TELEGRAF_RELEASE
    #TELEGRAF_UNCOMPRESSED='telegraf'  #

    # If we're on MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        TELEGRAF_PACKAGE=${TELEGRAF_RELEASE}_darwin_amd64 # for MacOS
    # If we're on Linux
    elif [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
        TELEGRAF_PACKAGE=${TELEGRAF_RELEASE}_linux_amd64 # for Linux
    else
        echo "ERROR: No Telegraf binary found for architecture \"`uname -s`\"."
        exit_gracefully
    fi
    TELEGRAF_URL=https://${TELEGRAF_REPO}/${TELEGRAF_PACKAGE}.tar.gz

    # Grab, uncompress and copy into place. We need to make a subdir
    # under /tmp because there's something strange with (at least the
    # current version of) the tar file which makes it try to change
    # the ctime of the directory it's in.
    mkdir -p /tmp/telegraf  #
    pushd /tmp/telegraf >> /dev/null
    if [ -e ${TELEGRAF_PACKAGE}.tar.gz ]; then
        echo Already have archive locally: /tmp/${TELEGRAF_PACKAGE}.tar.gz
    else
        echo Fetching binaries
        wget $TELEGRAF_URL
    fi
    if [ -d ${TELEGRAF_UNCOMPRESSED} ]; then
        echo Already have uncompressed release locally: /tmp/${TELEGRAF_RELEASE}
    else
        echo Uncompressing...
        tar xzf ${TELEGRAF_PACKAGE}.tar.gz
    fi

    echo Copying into place...
    if [ $OS_TYPE == 'MacOS' ]; then
        cp -rf ${TELEGRAF_UNCOMPRESSED} /usr/local/etc/telegraf
        ln -fs /usr/local/etc/telegraf/usr/bin/telegraf /usr/local/bin
    # If we're on Linux
    elif [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
        CURRENT_USER=$USER
        sudo cp -rf ${TELEGRAF_UNCOMPRESSED} /usr/local/etc/telegraf
        sudo ln -fs /usr/local/etc/telegraf/usr/bin/telegraf /usr/local/bin
        sudo chown -R $CURRENT_USER /usr/local/etc/telegraf
    fi
    popd >> /dev/null

    echo Configuring Telegraf
    TELEGRAF_CONF=/usr/local/etc/telegraf/etc/telegraf/telegraf.conf

    # Make sure we've got an InfluxDB auth token
    get_influxdb_auth_token

    # Overwrite the default telegraf.conf with a minimal one that includes
    # our InfluxDB auth tokens.
    cat > $TELEGRAF_CONF <<EOF
# Minimal Telegraf configuration
[global_tags]
[agent]
  interval = "10s"
  round_interval = true
  metric_batch_size = 1000
  metric_buffer_limit = 10000
  collection_jitter = "0s"
  flush_interval = "10s"
  flush_jitter = "0s"
  precision = ""
  hostname = ""
  omit_hostname = false
[[inputs.cpu]]
  percpu = true
  totalcpu = true
  collect_cpu_time = false
  report_active = false
[[inputs.disk]]
  ignore_fs = ["tmpfs", "devtmpfs", "devfs", "iso9660", "overlay", "aufs", "squashfs"]
[[inputs.diskio]]
[[inputs.kernel]]
[[inputs.mem]]
[[inputs.processes]]
[[inputs.swap]]
[[inputs.system]]

[[outputs.influxdb_v2]]
   urls = ["http://127.0.0.1:8086"]
   token = "$INFLUXDB_AUTH_TOKEN"  # Token for authentication.
   organization = "$ORGANIZATION"  # InfluxDB organization to write to
   bucket = "_monitoring"  # Destination bucket to write into.
EOF

    echo Done setting up Telegraf!
}

###########################################################################
# Set up supervisord file to start/stop all the relevant scripts.
function set_up_supervisor {
    echo "#####################################################################"
    echo Setting up supervisord file...


    TMP_SUPERVISOR_FILE=/tmp/influx.ini

    if [ $OS_TYPE == 'MacOS' ]; then
        SUPERVISOR_FILE=/usr/local/etc/supervisor.d/influx.ini

    # If CentOS/Ubuntu/etc, different distributions hide them
    # different places. Sigh.
    elif [ $OS_TYPE == 'CentOS' ]; then
        SUPERVISOR_FILE=/etc/supervisord.d/influx.ini
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        SUPERVISOR_FILE=/etc/supervisor/conf.d/influx.conf
    else
        echo "ERROR: Unknown OS/architecture \"$OS_TYPE\"."
        exit_gracefully
    fi

    cat > $TMP_SUPERVISOR_FILE <<EOF
; Control file for InfluxDB, Grafana and Telegraf. Generated using the
; openrvdas/utils/install_influxdb.sh script
EOF

    ##########
    # If InfluxDB is installed, create an entry for it
    if [[ -e /usr/local/bin/influxd ]]; then
        INSTALLED_PROGRAMS=influxdb

        if [[ $RUN_INFLUXDB == 'yes' ]];then
            AUTOSTART_INFLUXDB=true
        else
            AUTOSTART_INFLUXDB=false
        fi
        cat >> $TMP_SUPERVISOR_FILE <<EOF

; Run InfluxDB
[program:influxdb]
command=/usr/local/bin/influxd --reporting-disabled
directory=/opt/openrvdas
autostart=$AUTOSTART_INFLUXDB
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/influxdb.stderr
user=$USER
EOF
    fi

    ##########
    # If Grafana is installed, create an entry for it. Grafana
    # requires all sorts of command line help, and the locations of
    # the files it needs depend on the system, so hunt around.
    if [[ -e /usr/local/bin/grafana-server ]]; then
        if [[ -z "$INSTALLED_PROGRAMS" ]];then
            INSTALLED_PROGRAMS=grafana
        else
            INSTALLED_PROGRAMS=${INSTALLED_PROGRAMS},grafana
        fi

        GRAFANA_HOMEPATH=/usr/local/etc/grafana

        if [[ $RUN_GRAFANA == 'yes' ]];then
            AUTOSTART_GRAFANA=true
        else
            AUTOSTART_GRAFANA=false
        fi
        cat >> $TMP_SUPERVISOR_FILE <<EOF

; Run Grafana
[program:grafana]
command=/usr/local/bin/grafana-server --homepath $GRAFANA_HOMEPATH
directory=/opt/openrvdas
autostart=$AUTOSTART_GRAFANA
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/grafana.stderr
user=$USER
EOF
    fi

    ##########
    # If Telegraf is installed, create an entry for it.
    if [[ -e /usr/local/bin/telegraf ]]; then
        if [[ -z "$INSTALLED_PROGRAMS" ]];then
            INSTALLED_PROGRAMS=telegraf
        else
            INSTALLED_PROGRAMS=${INSTALLED_PROGRAMS},telegraf
        fi

        TELEGRAF_CONF=/usr/local/etc/telegraf/etc/telegraf/telegraf.conf

        if [[ $RUN_TELEGRAF == 'yes' ]];then
            AUTOSTART_TELEGRAF=true
        else
            AUTOSTART_TELEGRAF=false
        fi
        cat >> $TMP_SUPERVISOR_FILE <<EOF

; Run Telegraf
[program:telegraf]
command=/usr/local/bin/telegraf --config=${TELEGRAF_CONF}
directory=/opt/openrvdas
autostart=$AUTOSTART_TELEGRAF
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/telegraf.stderr
user=$USER
EOF
    fi

    cat >> $TMP_SUPERVISOR_FILE <<EOF

[group:influx]
programs=$INSTALLED_PROGRAMS
EOF
    sudo cp -f $TMP_SUPERVISOR_FILE $SUPERVISOR_FILE

    echo Done setting up supervisor files. Reloading...
    supervisorctl reload
}

###########################################################################

###########################################################################
###########################################################################
# Start of actual script
###########################################################################
###########################################################################

# Figure out what type of OS we've got running
get_os_type

# Read from the preferences file in $PREFERENCES_FILE, if it exists
set_default_variables

if [ "$(whoami)" == "root" ]; then
  echo "ERROR: installation script must NOT be run as root."
  exit_gracefully
fi

# Set creation mask so that everything we install is, by default,
# world readable/executable.
umask 022

echo "#####################################################################"
echo InfluxDB/Grafana/Telegraf configuration script

echo "#####################################################################"
read -p "Path to openrvdas directory? ($DEFAULT_INSTALL_ROOT) " INSTALL_ROOT
INSTALL_ROOT=${INSTALL_ROOT:-$DEFAULT_INSTALL_ROOT}
echo "Activating virtual environment in '${INSTALL_ROOT}/openrvdas'"
source $INSTALL_ROOT/openrvdas/venv/bin/activate

yes_no "Install InfluxDB?" $DEFAULT_INSTALL_INFLUXDB
INSTALL_INFLUXDB=$YES_NO_RESULT
if [ $INSTALL_INFLUXDB == "yes" ]; then
  yes_no "Run InfluxDB on boot?" $DEFAULT_RUN_INFLUXDB
  RUN_INFLUXDB=$YES_NO_RESULT
else
  RUN_INFLUXDB=no
fi

yes_no "Install Grafana?" $DEFAULT_INSTALL_GRAFANA
INSTALL_GRAFANA=$YES_NO_RESULT
if [ $INSTALL_GRAFANA == "yes" ]; then
  yes_no "Run Grafana on boot?" $DEFAULT_RUN_GRAFANA
  RUN_GRAFANA=$YES_NO_RESULT
else
  RUN_GRAFANA=no
fi

yes_no "Install Telegraf?" $DEFAULT_INSTALL_TELEGRAF
INSTALL_TELEGRAF=$YES_NO_RESULT
if [ $INSTALL_TELEGRAF == "yes" ]; then
  yes_no "Run Telegraf on boot?" $DEFAULT_RUN_TELEGRAF
  RUN_TELEGRAF=$YES_NO_RESULT
else
  RUN_TELEGRAF=no
fi

echo "#####################################################################"
echo "This script will create an InfluxDB user and set its password as you"
echo "specify. It will also set the password for Grafana's 'admin' account"
echo "to this password. However, Grafana has no command line mechanism for"
echo "creating new users, so you will need to either use Grafana's 'admin'"
echo "account or use Grafana's web interface (at hostname:3000) to manually"
echo "create a new user."
echo
read -p "InfluxDB user to create? ($DEFAULT_INFLUXDB_USER) " INFLUXDB_USER
INFLUXDB_USER=${INFLUXDB_USER:-$DEFAULT_INFLUXDB_USER}

while true; do
    echo
    echo "Passwords for InfluxDB must be at least 8 characters long."
    echo
    read -p "Password to use for user $INFLUXDB_USER? ($DEFAULT_INFLUXDB_PASSWORD) " INFLUXDB_PASSWORD
    INFLUXDB_PASSWORD=${INFLUXDB_PASSWORD:-$DEFAULT_INFLUXDB_PASSWORD}
    if [ ${#INFLUXDB_PASSWORD} -ge 8 ]; then
      break
    fi
done

read -p "HTTP/HTTPS proxy to use ($DEFAULT_HTTP_PROXY)? " HTTP_PROXY
HTTP_PROXY=${HTTP_PROXY:-$DEFAULT_HTTP_PROXY}

#########################################################################
# Save defaults in a preferences file for the next time we run.
save_default_variables

[ -z $HTTP_PROXY ] || echo Setting up proxy $HTTP_PROXY
[ -z $HTTP_PROXY ] || export http_proxy=$HTTP_PROXY
[ -z $HTTP_PROXY ] || export https_proxy=$HTTP_PROXY

#########################################################################

# Don't want existing installations to be running while we do this
echo Stopping supervisor prior to installation.
supervisorctl stop all

# Let's get to installing things!
if [ $INSTALL_INFLUXDB == 'yes' ];then
    install_influxdb
fi

if [ $INSTALL_GRAFANA == 'yes' ];then
    install_grafana
fi

if [ $INSTALL_TELEGRAF == 'yes' ];then
    install_telegraf
fi

open_required_ports

set_up_supervisor

#########################################################################
# Deactivate the virtual environment - we'll be calling all relevant
# binaries using their venv paths, so don't need it.
echo Deactivating virtual environment
deactivate

echo "#########################################################################"
echo Installation complete - happy logging!
echo
