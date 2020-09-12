#!/bin/bash -e

# OpenRVDAS is available as open source under the MIT License at
#   https:/github.com/oceandatatools/openrvdas
#
# This script installs and configures InfluxDB, Grafana (and
# optionally Telegraf) and creates a supervisord file that allows them
# to be started/stopped by supervisorctl. It should be run as the user
# who will be running OpenRVDAS (e.g. 'rvdas').
#
# The script has been designed to be idempotent, that is, if can be
# run over again with no ill effects.
#
# Once installed, you should be able to start/stop/disable the
# relevant services using supervisorctl.
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
# Read any pre-saved default variables from file
function set_default_variables {
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

    DEFAULT_RUN_INFLUXDB=yes
    DEFAULT_RUN_GRAFANA=yes
    DEFAULT_RUN_TELEGRAF=yes

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
###########################################################################
# Side routine we need for MacOS and InfluxDB. The standard brew
# package for InfluxDB is v1.8, so we need to create our own formula
# for grabbing and bottling up v2.
function create_influx_bottle {
    # Counts on INFLUXDB_URL being defined

    cat > /usr/local/Homebrew/Library/Taps/homebrew/homebrew-core/Formula/influxdbv2.rb <<EOF
class Influxdbv2 < Formula
  desc "Time series, events, and metrics database"
  homepage "https://influxdata.com/time-series-platform/influxdb/"
  url "${INFLUXDB_URL}"
  #sha256 "47fd524ffa5512601f417e01349cb5efbc0b4e13d891d2b52260092b323fb979"
  license "MIT"
  head "https://github.com/influxdata/influxdb.git"

  livecheck do
    url "https://github.com/influxdata/influxdb/releases/latest"
    regex(%r{href=.*?/tag/v?(\d+(?:\.\d+)+)["' >]}i)
  end

  bottle do
    cellar :any_skip_relocation
    sha256 "85487c01ca5b011374652ddb0dd4396d7f60cbc0227c8acef71caefea59d49d0" => :catalina
    sha256 "84de2bb9137efe42a18464023160dbc620053aa43bfb7dc03aa5234a7d337bd3" => :mojave
    sha256 "791fb60441f7ff352f0e4e929d02b7d472af56b200630ff90d42c195865fec5a" => :high_sierra
  end

  depends_on "go" => :build

  def install
    ENV["GOBIN"] = buildpath

    system "go", "install", "-ldflags", "-X main.version=#{version}", "./..."
    bin.install %w[influxd influx]

    (var/"influxdb/data").mkpath
    (var/"influxdb/meta").mkpath
    (var/"influxdb/wal").mkpath
  end

  plist_options manual: "influxd --reporting-disabled"

  def plist
    <<~EOS
      <?xml version="1.0" encoding="UTF-8"?>
      <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
      <plist version="1.0">
        <dict>
          <key>KeepAlive</key>
          <dict>
            <key>SuccessfulExit</key>
            <false/>
          </dict>
          <key>Label</key>
          <string>#{plist_name}</string>
          <key>ProgramArguments</key>
          <array>
            <string>#{opt_bin}/influxd</string>
            <string>--reporting-disabled</string>
          </array>
          <key>RunAtLoad</key>
          <false}/>
          <key>WorkingDirectory</key>
          <string>#{var}</string>
          <key>StandardErrorPath</key>
          <string>#{var}/log/influxdb.log</string>
          <key>StandardOutPath</key>
          <string>#{var}/log/influxdb.log</string>
          <key>SoftResourceLimits</key>
          <dict>
            <key>NumberOfFiles</key>
            <integer>10240</integer>
          </dict>
        </dict>
      </plist>
    EOS
  end
end
EOF
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
    else
        echo Retrieved InfluxDB auth token: $INFLUXDB_AUTH_TOKEN
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

    # If we're on MacOS, use brew. We need to bottle our own copy of
    # InfluxDB to get V2.
    if [ `uname -s` = 'Darwin' ]; then
        INFLUXDB_RELEASE=influxdb_2.0.0-beta.15_darwin_amd64 # for MacOS
        INFLUXDB_URL=https://$INFLUXDB_REPO/${INFLUXDB_RELEASE}.tar.gz
        create_influx_bottle
        brew reinstall influxdbv2

    # If we're on Linux, grab and copy
    elif [ `uname -s` = 'Linux' ]; then
        INFLUXDB_RELEASE=influxdb_2.0.0-beta.15_linux_amd64 # for Linux
        INFLUXDB_URL=http://$INFLUXDB_REPO/${INFLUXDB_RELEASE}.tar.gz

        pushd /tmp
        if [ -e ${INFLUXDB_RELEASE}.tar.gz ]; then
            echo Already have archive locally: /tmp/${INFLUXDB_RELEASE}.tar.gz
        else
            echo Fetching binaries
            wget $INFLUXDB_URL
        fi
        if [ -d ${INFLUXDB_RELEASE} ]; then
            echo Already have uncompressed release locally: /tmp/${INFLUXDB_RELEASE}
        else
            echo Uncompressing...
            tar xzf ${INFLUXDB_RELEASE}.tar.gz
        fi
        echo Copying into place...
        cp -f  ${INFLUXDB_RELEASE}/influx ${INFLUXDB_RELEASE}/influxd /usr/local/bin
        popd

    # If not MacOS and not Linux, we don't know how to install InfluxDB
    else
        echo "ERROR: No InfluxDB binary found for architecture \"`uname -s`\"."
        exit_gracefully
    fi

    # Run setup
    echo "#################################################################"
    echo Running InfluxDB setup - killing all currently-running instances
    killall influxd || echo no processes killed
    echo Running server in background
    /usr/local/bin/influxd --reporting-disabled > /dev/null &
    echo Sleeping to give server time to start up
    sleep 15
    echo Running influx setup
    /usr/local/bin/influx setup \
        --username $INFLUXDB_USER --password $INFLUXDB_PASSWORD \
        --org openrvdas --bucket openrvdas --retention 0 --force # > /dev/null
    echo Killing the InfluxDB instance we started
    killall influxd || echo no processes killed

    # Make sure setup succeeded by trying to get auth token
    get_influxdb_auth_token
    if [[ -z "$INFLUXDB_AUTH_TOKEN" ]];then
        echo Failed to get InfluxDB auth token - setup failed!
        exit_gracefully
    fi

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
    GRAFANA_RELEASE=grafana-7.1.5
    GRAFANA_URL=dl.grafana.com/oss/release

    if [ `uname -s` = 'Darwin' ]; then
        brew reinstall grafana

        echo Downloading plugins
        /usr/local/bin/grafana-cli --pluginsDir /usr/local/var/lib/grafana/plugins plugins install grafana-influxdb-flux-datasource
        /usr/local/bin/grafana-cli --pluginsDir /usr/local/var/lib/grafana/plugins plugins install briangann-gauge-panel

    # If CentOS/Ubuntu/etc, use
    elif [ `uname -s` = 'Linux' ]; then
        sdfasdf
        chown -R grafana /var/lib/grafana/plugins/
        chgrp -R grafana /var/lib/grafana/plugins/

    else
        echo "ERROR: Unknown OS/architecture \"`uname -s`\"."
        exit_gracefully
    fi

    echo Done setting up Grafana!
}

###########################################################################
# Tweak the telegraf.conf file to fit our installation
function fix_telegraf_conf {
    TELEGRAF_CONF=$1
    ORGANIZATION=openrvdas
    BUCKET=openrvdas

    # Make sure we've got an InfluxDB auth token
    get_influxdb_auth_token
    if [[ -z "$INFLUXDB_AUTH_TOKEN" ]];then
        echo Failed to get InfluxDB auth token - Telegraf setup failed!
        exit_gracefully
    fi

    sed -i -e "s/\[\[outputs.influxdb\]\]/\#\[\[outputs.influxdb\]\]/" $TELEGRAF_CONF
    sed -i -e "s/# \[\[outputs.influxdb_v2\]\]/\[\[outputs.influxdb_v2\]\]/" $TELEGRAF_CONF
    sed -i -e "s/#   token = \"\"/   token = \"${INFLUXDB_AUTH_TOKEN}\"/" $TELEGRAF_CONF
    sed -i -e "s/#   organization = \"\"/   organization = \"$ORGANIZATION\"/" $TELEGRAF_CONF
    sed -i -e "s/#   bucket = \"\"/   bucket = \"$BUCKET\"/" $TELEGRAF_CONF
}

###########################################################################
# Install and configure Telegraf - to be run *after* OpenRVDAS is in place!
function install_telegraf {
    echo "#####################################################################"
    echo Installing Telegraf...

    if [ `uname -s` = 'Darwin' ]; then
        brew reinstall telegraf
        fix_telegraf_conf /usr/local/etc/telegraf.conf

    # If CentOS/Ubuntu/etc, use
    elif [ `uname -s` = 'Linux' ]; then
        sdfasdf

    else
        echo "ERROR: Unknown OS/architecture \"`uname -s`\"."
        exit_gracefully
    fi

    echo Done setting up Grafana!
}

###########################################################################
# Set up supervisord file to start/stop all the relevant scripts.
function set_up_supervisor {
    echo "#####################################################################"
    echo Setting up supervisord file...

    if [ `uname -s` = 'Darwin' ]; then
        SUPERVISOR_FILE=/usr/local/etc/supervisor.d/influx.ini

    # If CentOS/Ubuntu/etc, different distributions hide them
    # different places. Sigh.
    elif [ `uname -s` = 'Linux' ]; then
        if [[ -d /etc/supervisor/conf.d ]];then
            SUPERVISOR_FILE=/etc/supervisor/conf.d/influx.conf
        elif [[ -d /etc/supervisor.d ]];then
            SUPERVISOR_FILE=/etc/supervisor.d/influx.ini
        else
            echo "Can't figure where to put control file for supervisor!"
            exit_gracefully
        fi
    else
        echo "ERROR: Unknown OS/architecture \"`uname -s`\"."
        exit_gracefully
    fi

    cat > $SUPERVISOR_FILE <<EOF
; Control file for InfluxDB, Grafana and Telegraf. Generated using the
; openrvdas/utils/install_influxdb.sh script
EOF

    ##########
    # If InfluxDB is installed, create an entry for it
    if [[ -e /usr/local/bin/influxd ]]; then
        if [[ $RUN_INFLUXDB == 'yes' ]];then
            AUTOSTART_INFLUXDB=true
        else
            AUTOSTART_INFLUXDB=false
        fi
        cat >> $SUPERVISOR_FILE <<EOF

; Run InfluxDB
[program:influxdb]
command=/usr/local/bin/influxd --reporting-disabled
directory=/opt/openrvdas
autostart=$AUTOSTART_INFLUXDB
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/influxdb.stderr
EOF
    fi

    ##########
    # If Grafana is installed, create an entry for it. Grafana
    # requires all sorts of command line help, and the locations of
    # the files it needs depend on the system, so hunt around.
    if [[ -e /usr/local/bin/grafana-server ]]; then
        # Find Grafana config
        if [[ -e /etc/grafana/grafana.ini ]];then
            GRAFANA_INI=/etc/grafana/grafana.ini
        elif [[ -e /usr/local/etc/grafana/grafana.ini ]];then
            GRAFANA_INI=/usr/local/etc/grafana/grafana.ini
        else
            echo "Can't find grafana.ini file!"
            exit_gracefully
        fi
        # Find Grafana plugins
        if [[ -d /var/lib/grafana/plugins ]];then
            GRAFANA_PLUGINS=/var/lib/grafana/plugins
        elif [[ -d /usr/local/var/lib/grafana/plugins ]];then
            GRAFANA_PLUGINS=/usr/local/var/lib/grafana/plugins
        else
            echo "Can't find grafana plugins!"
            exit_gracefully
        fi
        # Find homepath
        if [[ -d /usr/share/grafana ]];then
            GRAFANA_HOMEPATH=/usr/share/grafana
        elif [[ -d /usr/local/opt/grafana/share/grafana ]];then
            GRAFANA_HOMEPATH=/usr/local/opt/grafana/share/grafana
        else
            echo "Can't find grafana homepath!"
            exit_gracefully
        fi

        if [[ $RUN_GRAFANA == 'yes' ]];then
            AUTOSTART_GRAFANA=true
        else
            AUTOSTART_GRAFANA=false
        fi
        cat >> $SUPERVISOR_FILE <<EOF

; Run Grafana
[program:grafana]
command=/usr/local/bin/grafana-server --config=${GRAFANA_INI} --homepath $GRAFANA_HOMEPATH cfg:default.paths.plugins=${GRAFANA_PLUGINS}
directory=/opt/openrvdas
autostart=$AUTOSTART_GRAFANA
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/grafana.stderr
EOF
    fi

    ##########
    # If Telegraf is installed, create an entry for it.
    if [[ -e /usr/local/bin/telegraf ]]; then
        # Find Telegraf config
        if [[ -e /etc/telegraf.conf ]];then
            TELEGRAF_CONFIG=/etc/telegraf.conf
        elif [[ -e /usr/local/etc/telegraf.conf ]];then
            TELEGRAF_CONFIG=/usr/local/etc/telegraf.conf
        else
            echo "Can't find telegraf.conf file!"
            exit_gracefully
        fi
        # Find Telegraf plugins
        if [[ -d /etc/telegraf/telegraf.d ]];then
            TELEGRAF_DIR=/etc/telegraf/telegraf.d
        elif [[ -d /usr/local/etc/telegraf.d ]];then
            TELEGRAF_DIR=/usr/local/etc/telegraf.d
        else
            echo "Can't find telegraf config directory!"
            exit_gracefully
        fi

        if [[ $RUN_TELEGRAF == 'yes' ]];then
            AUTOSTART_TELEGRAF=true
        else
            AUTOSTART_TELEGRAF=false
        fi
        cat >> $SUPERVISOR_FILE <<EOF

; Run Telegraf
[program:telegraf]
command=/usr/local/bin/telegraf --config=${TELEGRAF_CONFIG} --config-directory $TELEGRAF_DIR
directory=/opt/openrvdas
autostart=$AUTOSTART_TELEGRAF
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/telegraf.stderr
EOF
    fi

    cat >> $SUPERVISOR_FILE <<EOF

[group:influx]
programs=influxdb,grafana,telegraf
EOF
    echo Done setting up supervisor files. Please restart/reload supervisor
    echo for changes to take effect!
}

###########################################################################

###########################################################################
###########################################################################
# Start of actual script
###########################################################################
###########################################################################

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
read -p "InfluxDB user to create? ($DEFAULT_INFLUXDB_USER) " INFLUXDB_USER
INFLUXDB_USER=${INFLUXDB_USER:-$DEFAULT_INFLUXDB_USER}
read -p "Password to use for user $INFLUXDB_USER? ($DEFAULT_INFLUXDB_PASSWORD) " INFLUXDB_PASSWORD
INFLUXDB_PASSWORD=${INFLUXDB_PASSWORD:-$DEFAULT_INFLUXDB_PASSWORD}

read -p "HTTP/HTTPS proxy to use ($DEFAULT_HTTP_PROXY)? " HTTP_PROXY
HTTP_PROXY=${HTTP_PROXY:-$DEFAULT_HTTP_PROXY}

#########################################################################
# Save defaults in a preferences file for the next time we run.
save_default_variables

[ -z $HTTP_PROXY ] || echo Setting up proxy $HTTP_PROXY
[ -z $HTTP_PROXY ] || export http_proxy=$HTTP_PROXY
[ -z $HTTP_PROXY ] || export https_proxy=$HTTP_PROXY

#########################################################################
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

set_up_supervisor

#########################################################################
# Deactivate the virtual environment - we'll be calling all relevant
# binaries using their venv paths, so don't need it.
echo Deactivating virtual environment
deactivate

echo "#########################################################################"
echo Installation complete - happy logging!
echo
