#!/bin/bash -e

# OpenRVDAS is available as open source under the MIT License at
#   https:/github.com/oceandatatools/openrvdas
#
# This script installs and configures InfluxDB, Grafana (and
# optionally Telegraf), installs them as system services and makes the
# necessary arrangements for OpenRVDAS to feed data to InfluxDB.  It
# is designed to be run as root.
#
# The script has been designed to be idempotent, that is, if can be
# run over again with no ill effects.
#
# Once installed, you should be able to start/stop/disable the
# relevant services using either systemctl (Linux) or brew services
# (MacOS):
#
# systemctl [command] [service]
#
# where command is one of
#  - stop/start/restart - stop/start/restart the running server
#  - enable/disable - set the server to start on system startup (or not)
#
# and service is one of
#  - influxdb
#  - grafana-server
#  - telegraf
#
# For MacOS, use 'brew services' instead of 'systemctl'
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
    # Counts on INFLUXDB_URL and RUN_INFLUXDB being defined
    if [ $RUN_INFLUXDB == "yes" ];then
        RUN_AT_LOAD=true
    else
        RUN_AT_LOAD=false
    fi

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
          <${RUN_AT_LOAD}/>
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
    
    # If we're on MacOS, use brew. We need to bottle our own copy of
    # InfluxDB to get V2.
    if [ `uname -s` = 'Darwin' ]; then
        if [ -d ~/.influxdbv2 ];then
            echo
            echo "An installation of InfluxDB appears to already exist. Overwriting"
            echo "Will reset any existing tokens and require resetting connections "
            echo "From all Grafana and Telegraf servers."
            yes_no "Overwrite existing installation?" no
            if [ $YES_NO_RESULT == 'no' ];then
                return 0
            fi
        fi
        
        # If here, we're installing new or overwriting the existing installation.
        # Clear out any old setup directories.
        rm -rf ~/.influxdbv2

        INFLUXDB_RELEASE=influxdb_2.0.0-beta.15_darwin_amd64 # for MacOS
        INFLUXDB_URL=https://$INFLUXDB_REPO/${INFLUXDB_RELEASE}.tar.gz
        create_influx_bottle
        brew reinstall influxdbv2

        # We need to start influxdb up to do setup
        brew services restart influxdbv2

        echo Sleeping to give InfluxDB time to start up
        sleep 15
        echo Running influx setup
        /usr/local/bin/influx setup \
          --username $INFLUXDB_USER --password $INFLUXDB_PASSWORD \
          --org openrvdas --bucket openrvdas --retention 0 --force # > /dev/null

        echo Getting auth token
        INFLUXDB_AUTH_TOKEN=`/usr/local/bin/influx auth list | grep $INFLUXDB_USER | cut -f2`
        # Copy the auth token into database settings
        sed -i -e "s/INFLUXDB_AUTH_TOKEN = '.*'/INFLUXDB_AUTH_TOKEN = '${INFLUXDB_AUTH_TOKEN}'/" $INSTALL_ROOT/openrvdas/database/settings.py

        # Now shut down server if we've not been asked to keep it
        # running.
        if [ $RUN_INFLUXDB == 'yes' ];then
            brew services start influxdbv2
        else
            brew services stop influxdbv2
        fi
        
    # If we're on Linux, grab and copy
    elif [ `uname -s` = 'Linux' ]; then
        INFLUXDB_RELEASE=influxdb_2.0.0-beta.15_linux_amd64 # for Linux
        INFLUXDB_URL=http://$INFLUXDB_REPO/${INFLUXDB_RELEASE}.tar.gz

        # Check if we've already got an installation, and give user an
        # option to skip if they don't want to clobber it and install over
        # it.
        if [ -e '/usr/local/bin/influx' ]; then
            echo
            echo "An installation of InfluxDB appears to already exist. Overwriting"
            echo "Will reset any existing tokens and require resetting connections "
            echo "From all Grafana and Telegraf servers."
            yes_no "Overwrite existing installation?" no
            if [ $YES_NO_RESULT == 'no' ];then
                return 0
            fi
        fi
        
        # If here, we're installing new or overwriting the existing installation.
        # Clear out any old setup directories.
        rm -rf ~/.influxdbv2 /var/root/.influxdbv2 /private/var/root/.influxdbv2/configs
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

        echo Need systemctl stuff for InfluxDB!!!!!!
        
    # If not MacOS and not Linux, we don't know how to install InfluxDB
    else
        echo "ERROR: No InfluxDB binary found for architecture \"`uname -s`\"."
        exit_gracefully
    fi

    echo "#################################################################"
    # Install the InfluxDB python client
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
        sudo /usr/local/bin/grafana-cli --pluginsDir /usr/local/var/lib/grafana/data/plugins plugins install grafana-influxdb-flux-datasource
        sudo /usr/local/bin/grafana-cli --pluginsDir /usr/local/var/lib/grafana/data/plugins plugins install briangann-gauge-panel

        if [ $RUN_GRAFANA == 'yes' ];then
            brew services start grafana
        fi

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
# An ugly, but necessary thing. We don't know if they've already set
# this, so we need to start up influxdb if it's not running, fetch it
# using auth, then return it to its prior state.
function set_influxdb_auth_token {
    if [[ -z "`brew services | grep influxdbv2 | grep stopped`" ]];then
        INFLUX_WAS_RUNNING=true
    else
        brew services start influxdbv2
        sleep 15
        INFLUX_WAS_RUNNING=false
    fi

    INFLUXDB_AUTH_TOKEN=`/usr/local/bin/influx auth list | grep $INFLUXDB_USER | cut -f2`

    if [ $INFLUX_WAS_RUNNING == "false" ];then
        brew services stop influxdbv2
    fi
}    

###########################################################################
# Tweak the telegraf.conf file to fit our installation
function fix_telegraf_conf {
    TELEGRAF_CONF=$1

    set_influxdb_auth_token
    echo HAVE TOKEN: $
    sed -i -e "s/\[\[outputs.influxdb\]\]/\#\[\[outputs.influxdb\]\]/" $TELEGRAF_CONF
    sed -i -e "s/# \[\[outputs.influxdb_v2\]\]/\[\[outputs.influxdb_v2\]\]/" $TELEGRAF_CONF
    sed -i -e "s/#   token = \"\"/   token = \"${INFLUXDB_AUTH_TOKEN}\"/" $TELEGRAF_CONF
    sed -i -e "s/#   organization = \"\"/   organization = \"openrvdas\"/" $TELEGRAF_CONF
    sed -i -e "s/#   bucket = \"\"/   bucket = \"openrvdas\"/" $TELEGRAF_CONF
}

###########################################################################
# Install and configure Telegraf - to be run *after* OpenRVDAS is in place!
function install_telegraf {
    echo "#####################################################################"
    echo Installing Telegraf...

    if [ `uname -s` = 'Darwin' ]; then
        brew reinstall telegraf
        fix_telegraf_conf /usr/local/etc/telegraf.conf

        if [ $RUN_TELEGRAF == 'yes' ];then
            brew services start telegraf
        fi

    # If CentOS/Ubuntu/etc, use 
    elif [ `uname -s` = 'Linux' ]; then
        sdfasdf

    else
        echo "ERROR: Unknown OS/architecture \"`uname -s`\"."
        exit_gracefully
    fi
    echo 7
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

#########################################################################
# Deactivate the virtual environment - we'll be calling all relevant
# binaries using their venv paths, so don't need it.
echo Deactivating virtual environment
deactivate

echo "#########################################################################"
echo Installation complete - happy logging!
echo
