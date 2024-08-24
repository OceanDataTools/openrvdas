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

DEFAULT_STANDALONE_INSTALLATION=no

DEFAULT_INFLUXDB_USER=rvdas
DEFAULT_INFLUXDB_PASSWORD=rvdasrvdas

DEFAULT_INFLUXDB_ORGANIZATION=openrvdas
DEFAULT_INFLUXDB_BUCKET=openrvdas

DEFAULT_INSTALL_INFLUXDB=yes
DEFAULT_INSTALL_GRAFANA=yes
DEFAULT_INSTALL_TELEGRAF=yes

DEFAULT_RUN_INFLUXDB=no
DEFAULT_RUN_GRAFANA=no
DEFAULT_RUN_TELEGRAF=no

DEFAULT_USE_SSL=no
DEFAULT_HAVE_SSL_CERTIFICATE=no
DEFAULT_SSL_CRT_LOCATION=${DEFAULT_INSTALL_ROOT}/openrvdas/openrvdas.crt
DEFAULT_SSL_KEY_LOCATION=${DEFAULT_INSTALL_ROOT}/openrvdas/openrvdas.key

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
        # CentOS/RHEL
        elif [[ ! -z `grep "NAME=\"CentOS Stream\"" /etc/os-release` ]] || [[ ! -z `grep "NAME=\"CentOS Linux\"" /etc/os-release` ]] || [[ ! -z `grep "NAME=\"Red Hat Enterprise Linux\"" /etc/os-release` ]]  || [[ ! -z `grep "NAME=\"Rocky Linux\"" /etc/os-release` ]];then
            OS_TYPE=CentOS
            if [[ ! -z `grep "VERSION_ID=\"7" /etc/os-release` ]];then
                OS_VERSION=7
            elif [[ ! -z `grep "VERSION_ID=\"8" /etc/os-release` ]];then
                OS_VERSION=8
            elif [[ ! -z `grep "VERSION_ID=\"9" /etc/os-release` ]];then
                OS_VERSION=9
            # Rocky Linux uses different format in /etc/os-release
            elif [[ ! -z `grep "VERSION=\"7" /etc/os-release` ]];then
                OS_VERSION=7
            elif [[ ! -z `grep "VERSION=\"8" /etc/os-release` ]];then
                OS_VERSION=8
            elif [[ ! -z `grep "VERSION=\"9" /etc/os-release` ]];then
                OS_VERSION=9
            else
                echo "Sorry - unknown CentOS/RHEL Version! - exiting."
                exit_gracefully
            fi
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

DEFAULT_STANDALONE_INSTALLATION=$STANDALONE_INSTALLATION

DEFAULT_INFLUXDB_USER=$INFLUXDB_USER
DEFAULT_INFLUXDB_PASSWORD=$INFLUXDB_PASSWORD
DEFAULT_INFLUXDB_ORGANIZATION=$INFLUXDB_ORGANIZATION
DEFAULT_INFLUXDB_BUCKET=$INFLUXDB_BUCKET

DEFAULT_INSTALL_INFLUXDB=$INSTALL_INFLUXDB
DEFAULT_INSTALL_GRAFANA=$INSTALL_GRAFANA
DEFAULT_INSTALL_TELEGRAF=$INSTALL_TELEGRAF

DEFAULT_RUN_INFLUXDB=$RUN_INFLUXDB
DEFAULT_RUN_GRAFANA=$RUN_GRAFANA
DEFAULT_RUN_TELEGRAF=$RUN_TELEGRAF

DEFAULT_USE_SSL=$USE_SSL
DEFAULT_HAVE_SSL_CERTIFICATE=$HAVE_SSL_CERTIFICATE
DEFAULT_SSL_CRT_LOCATION=$SSL_CRT_LOCATION
DEFAULT_SSL_KEY_LOCATION=$SSL_KEY_LOCATION
EOF
}

###########################################################################
###########################################################################
# Create user
function create_user {
    RVDAS_USER=$1

    echo Checking if user $RVDAS_USER exists yet
    if id -u $RVDAS_USER > /dev/null; then
        echo User "$RVDAS_USER" exists
    else
        # MacOS
        if [ $OS_TYPE == 'MacOS' ]; then
          echo No such pre-existing user: $RVDAS.
          echo On MacOS, must install for pre-existing user. Exiting.
          exit_gracefully

        # CentOS/RHEL
        elif [ $OS_TYPE == 'CentOS' ]; then
            echo Creating $RVDAS_USER
            sudo adduser $RVDAS_USER
            sudo passwd $RVDAS_USER

        # Ubuntu/Debian
        elif [ $OS_TYPE == 'Ubuntu' ]; then
              echo Creating $RVDAS_USER
              sudo adduser --gecos "" $RVDAS_USER
        fi
    fi

    # Set up user permissions, whether or not pre-existing.
    # For MacOS we don't change anything
    if [ $OS_TYPE == 'CentOS' ]; then
        sudo usermod -a -G tty $RVDAS_USER
        sudo usermod -a -G wheel $RVDAS_USER

    # Ubuntu/Debian
    elif [ $OS_TYPE == 'Ubuntu' ]; then
          sudo usermod -a -G tty $RVDAS_USER
          sudo usermod -a -G dialout $RVDAS_USER
          sudo usermod -a -G sudo $RVDAS_USER
    fi
}

###########################################################################
###########################################################################
# Install and configure required packages
function install_packages {

    # MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        # Install Homebrew - note: reinstalling is idempotent
        echo 'Installing XCode Tools'
        xcode-select --install || echo "XCode Tools already installed"
        pushd /tmp
        HOMEBREW_VERSION=4.1.21
        HOMEBREW_TARGET=Homebrew-${HOMEBREW_VERSION}.pkg
        HOMEBREW_PATH=https://github.com/Homebrew/brew/releases/download/${HOMEBREW_VERSION}/${HOMEBREW_TARGET}

        curl -O -L ${HOMEBREW_PATH}

        # The -target / specifies that the package should be installed on the root volume.
        sudo installer -pkg ${HOMEBREW_TARGET} -target /
        popd

        brew install python git nginx supervisor

        #brew upgrade openssh nginx supervisor || echo Upgraded packages
        #brew link --overwrite python || echo Linking Python

    # CentOS/RHEL
    elif [ $OS_TYPE == 'CentOS' ]; then
        if [ $OS_VERSION == '7' ]; then
            sudo yum install -y deltarpm
        fi

        # Check if EPEL repository is installed by trying to install supervisor
        if dnf list available supervisor --enablerepo=epel &> /dev/null; then
            echo "EPEL is already available - skipping installation."
        else
          sudo dnf install -y epel-release
          if [ $? -eq 0 ]; then
            echo "EPEL repository installed successfully."
          else
            echo "Failed to install EPEL repository."
            exit 1
          fi
        fi
        sudo yum -y update

        echo Installing required packages
        sudo yum install -y wget git nginx gcc supervisor \
            zlib-devel openssl-devel readline-devel libffi-devel \
            sqlite libsqlite3x-devel

            #sqlite-devel \
            #python3 python3-devel python3-pip

        # Django 3+ requires a more recent version of sqlite3 than is
        # included in CentOS 7. So instead of yum installing python3 and
        # sqlite3, we build them from scratch. Painfully slow, but hey -
        # isn't that par for CentOS builds?
        export LD_LIBRARY_PATH=/usr/local/lib
        export LD_RUN_PATH=/usr/local/lib

        # Check if correct SQLite3 is installed
        SQLITE_VERSION=3320300
        #required_version="3.32.3"

        if ! command -v sqlite3 &> /dev/null
        then
            echo "SQLite3 is not installed. Installing ..."
            sudo yum install -y sqlite sqlite-devel
#        else
#            # Get the current version of SQLite3
#            current_version=$(sqlite3 --version | awk '{print $1}')
#
#            # Compare the current version with the required version
#            if [[ "$current_version" != "$required_version" ]]
#            then
#                echo "SQLite3 version $required_version is required, but version $current_version is installed. Installing version $required_version..."
#                sudo yum install -y sqlite-$required_version sqlite-devel
#            else
#                echo "SQLite3 version $required_version is already installed."
#            fi
        fi

        if [ $OS_VERSION == '7' ] || [ $OS_VERSION == '8' ]; then
            # Build Python, too, if we don't have right version
            PYTHON_VERSION='3.8.3'
            if [ "`/usr/local/bin/python3 --version`" == "Python $PYTHON_VERSION" ]; then
                echo Already have appropriate version of Python3
            else
                OPENRVDAS_INSTALL_TMP_DIR=openrvdas_install_tmp
                mkdir $OPENRVDAS_INSTALL_TMP_DIR
                pushd $OPENRVDAS_INSTALL_TMP_DIR
                yum install -y make
                #cd /var/tmp    # Nope - some systems bar executing anything in /tmp
                PYTHON_BASE=Python-${PYTHON_VERSION}
                PYTHON_TGZ=${PYTHON_BASE}.tgz
                [ -e $PYTHON_TGZ ] || wget https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_TGZ}
                tar xvf ${PYTHON_TGZ}
                cd ${PYTHON_BASE}
                sh ./configure # --enable-optimizations
                sudo make altinstall

                sudo ln -s -f /usr/local/bin/python3.8 /usr/local/bin/python3
                sudo ln -s -f /usr/local/bin/pip3.8 /usr/local/bin/pip3
                popd
            fi
        elif [ $OS_VERSION == '8' ] || [ $OS_VERSION == '9' ]; then
            sudo yum install -y python3 python3-devel
        else
            echo "Install error: unknown OS_VERSION should have been caught earlier?!?"
            echo "OS_VERSION = \"$OS_VERSION\""
            exit_gracefully
        fi

    # Ubuntu/Debian
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        sudo apt-get update
        sudo apt install -y git nginx libreadline-dev \
            python3-dev python3-pip python3-venv libsqlite3-dev \
            openssh-server supervisor libssl-dev
    fi
}

###########################################################################
###########################################################################
# Install OpenRVDAS
function install_openrvdas {
    # Expect the following shell variables to be appropriately set:
    # INSTALL_ROOT - path where openrvdas/ is
    # RVDAS_USER - valid userid
    # OPENRVDAS_REPO - path to OpenRVDAS repo
    # OPENRVDAS_BRANCH - branch of rep to install

    if [ ! -d $INSTALL_ROOT ]; then
      echo "Making install directory \"$INSTALL_ROOT\""
      sudo mkdir -p $INSTALL_ROOT
      sudo chown ${RVDAS_USER} $INSTALL_ROOT
    fi

    cd $INSTALL_ROOT
    if [ ! -e openrvdas ]; then
      echo "Making openrvdas directory."
      sudo mkdir openrvdas
      sudo chown ${RVDAS_USER} openrvdas
    fi

    # If FIPS is active, we need this to prevent it from complaining
    git config --global --add safe.directory ${INSTALL_ROOT}/openrvdas

    if [ -e openrvdas/.git ] ; then   # If we've already got an installation
      cd openrvdas
      git pull
      git checkout $OPENRVDAS_BRANCH
      git pull
    else                              # If we don't already have an installation
      sudo rm -rf openrvdas           # in case there's a non-git dir there
      sudo mkdir openrvdas
      sudo chown ${RVDAS_USER} openrvdas
      git clone -b $OPENRVDAS_BRANCH $OPENRVDAS_REPO
      cd openrvdas
    fi

    # Copy widget settings into place and customize for this machine
    cp display/js/widgets/settings.js.dist \
       display/js/widgets/settings.js
    sed -i -e "s/= 'ws'/= '${WEBSOCKET_PROTOCOL}'/g" display/js/widgets/settings.js
    sed -i -e "s/localhost/${HOSTNAME}/g" display/js/widgets/settings.js
    sed -i -e "s/ = 80/ = ${SERVER_PORT}/g" display/js/widgets/settings.js

    # Copy the database settings.py.dist into place so that other
    # routines can make the modifications they need to it.
    cp database/settings.py.dist database/settings.py
    sed -i -e "s/DEFAULT_DATABASE_USER = 'rvdas'/DEFAULT_DATABASE_USER = '${RVDAS_USER}'/g" database/settings.py
    sed -i -e "s/DEFAULT_DATABASE_PASSWORD = 'rvdas'/DEFAULT_DATABASE_PASSWORD = '${RVDAS_DATABASE_PASSWORD}'/g" database/settings.py
}

###########################################################################
###########################################################################
# Set up certificate files, if requested
function setup_ssl_certificate {
    echo "Certificate will be placed in ${SSL_CRT_LOCATION}"
    echo "Key will be placed in ${SSL_KEY_LOCATION}"
    echo "Please answer the following prompts to continue:"
    echo
    openssl req \
       -newkey rsa:2048 -nodes -keyout ${SSL_KEY_LOCATION} \
       -x509 -days 365 -out ${SSL_CRT_LOCATION}
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

    sed -i -e "s/INFLUXDB_ORG = '.*'/INFLUXDB_ORG = '$INFLUXDB_ORGANIZATION'/" $SETTINGS
    sed -i -e "s/INFLUXDB_BUCKET = '.*'/INFLUXDB_BUCKET = '$INFLUXDB_BUCKET'/" $SETTINGS
    sed -i -e "s/INFLUXDB_AUTH_TOKEN = '.*'/INFLUXDB_AUTH_TOKEN = '$INFLUXDB_AUTH_TOKEN'/" $SETTINGS

    # If they've run this with an old installation of OpenRVDAS,
    # database/settings.py may have the old/wrong port number for InfluxDB
    sed -i -e "s/INFLUXDB_URL = 'http:\/\/localhost:9999'/INFLUXDB_URL = 'http:\/\/localhost:8086'/" $SETTINGS

    # If we're using SSL, change any "http" reference to "https"; if not
    # do vice versa.
    if [[ $USE_SSL == 'yes' ]];then
        sed -i -e "s/http:/https:/" $SETTINGS
    else
        sed -i -e "s/https:/http:/" $SETTINGS
    fi
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


    # If we're on MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        INFLUX_PATH=/usr/local/bin
    # If we're on Linux
    elif [ $OS_TYPE == 'CentOS' ]; then
        INFLUX_PATH=/usr/bin
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        INFLUX_PATH=/usr/bin
    else
        exit_gracefully
    fi

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

    # From https://docs.influxdata.com/influxdb/v2.2/install/?t=CLI+Setup

    # If we're on MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        brew update
        brew upgrade
        brew install --overwrite influxdb influxdb-cli

    # If we're on Linux
    elif [ $OS_TYPE == 'CentOS' ]; then
        # Remove old repo, if it's lying around
        if [ -e /etc/yum.repos.d/influxdb.repo ]; then
            sudo rm /etc/yum.repos.d/influxdb.repo
        fi
        # From https://portal.influxdata.com/downloads/
        # influxdata-archive_compat.key GPG fingerprint:
        #     9D53 9D90 D332 8DC7 D6C8 D3B9 D8FF 8E1F 7DF8 B07E
        cat <<EOF | sudo tee /etc/yum.repos.d/influxdata.repo
[influxdata]
name = InfluxData Repository - Stable
baseurl = https://repos.influxdata.com/stable/\$basearch/main
enabled = 1
gpgcheck = 1
gpgkey = https://repos.influxdata.com/influxdata-archive_compat.key
EOF
        if [ $OS_VERSION == '7' ]; then
            sudo yum install -y influxdb2 influxdb2-cli
        else
            # Need to accommodate FIPS in RHEL8, which will complain
            # if we try to MD5. Sheesh.
            # sudo yum install -y --nobest influxdb2 influxdb2-cli
            dnf download influxdb2 influxdb2-cli
            sudo rpm -ivh --nofiledigest --replacepkgs --replacefiles influxdb*.rpm
        fi
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        # influxdata-archive_compat.key GPG Fingerprint: 9D539D90D3328DC7D6C8D3B9D8FF8E1F7DF8B07E
        wget -q https://repos.influxdata.com/influxdata-archive_compat.key
        echo '393e8779c89ac8d958f81f942f9ad7fb82a25e133faddaf92e15b16e6ac9ce4c influxdata-archive_compat.key' | sha256sum -c && cat influxdata-archive_compat.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg > /dev/null
        echo 'deb [signed-by=/etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg] https://repos.influxdata.com/debian stable main' | sudo tee /etc/apt/sources.list.d/influxdata.list
        sudo apt-get update || echo "Failed to update all packages"

        sudo apt-get install -y influxdb2
    else
        echo "ERROR: No InfluxDB binary found for architecture \"`uname -s`\"."
        exit_gracefully
    fi

    # Run setup
    echo "#################################################################"
    echo Running InfluxDB setup - killing all currently-running instances
    sudo pkill -x influxd || echo No processes killed
    echo Running server in background
    ${INFLUX_PATH}/influxd --reporting-disabled > /dev/null &
    echo Sleeping to give server time to start up
    sleep 20  # if script crashes at next step, increase this number a smidge
    echo Running influx setup
    ${INFLUX_PATH}/influx setup \
        --username $INFLUXDB_USER --password $INFLUXDB_PASSWORD \
        --org $INFLUXDB_ORGANIZATION --bucket $INFLUXDB_BUCKET --retention 0 --force # > /dev/null

    #    echo Killing the InfluxDB instance we started
    sudo pkill -x influxd || echo No processes killed

    # We're going to run Influx from supervisorctl, so disable automatic service
    sudo systemctl stop influxd || echo influxd not loaded as a service, so nothing to stop
    sudo systemctl disable influxd || echo influxd not loaded as a service, so nothing to disable

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

    if [ $OS_TYPE == 'MacOS' ]; then
        GRAFANA_PATH=/usr/local/bin
        GRAFANA_HOMEPATH=/usr/local/share/grafana
        GRAFANA_CONFIG=/usr/local/share/grafana/conf/defaults.ini

        brew update
        brew upgrade
        brew install --overwrite grafana

    # If we're on CentOS
    elif [ $OS_TYPE == 'CentOS' ]; then
        GRAFANA_PATH=/usr/sbin
        GRAFANA_HOMEPATH=/usr/share/grafana
        GRAFANA_CONFIG=/usr/share/grafana/conf/defaults.ini

        cat <<EOF | sudo tee /etc/yum.repos.d/grafana.repo
[grafana]
name=grafana
baseurl=https://packages.grafana.com/oss/rpm
repo_gpgcheck=1
enabled=1
gpgcheck=1
gpgkey=https://packages.grafana.com/gpg.key
sslverify=1
sslcacert=/etc/pki/tls/certs/ca-bundle.crt
EOF
        sudo yum install -y grafana

    # If we're on Ubuntu
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        GRAFANA_PATH=/usr/sbin
        GRAFANA_HOMEPATH=/usr/share/grafana
        GRAFANA_CONFIG=/usr/share/grafana/conf/defaults.ini

        sudo apt-get install -y apt-transport-https
        sudo apt-get install -y software-properties-common wget
        sudo apt-get install -y software-properties-common wget
        wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
        echo "deb https://packages.grafana.com/oss/deb stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
        sudo apt-get update
        sudo apt-get install -y grafana

    fi

    pushd $GRAFANA_HOMEPATH
    sudo ${GRAFANA_PATH}/grafana-cli admin reset-admin-password $INFLUXDB_PASSWORD

    echo Downloading plugins
    sudo ${GRAFANA_PATH}/grafana-cli plugins install grafana-influxdb-flux-datasource
    sudo ${GRAFANA_PATH}/grafana-cli plugins install briangann-gauge-panel
    popd

    # If we're using SSL, change any "http" reference to "https"; if not
    # do vice versa.
    if [[ $USE_SSL == 'yes' ]];then
        sudo sed -i -e "s/protocol = http.*/protocol = https/" $GRAFANA_CONFIG
        sudo sed -i -e "s/ssl_mode =.*/ssl_mode = skip-verify/" $GRAFANA_CONFIG
        # Filepath contains '/', so use '#' for sed delimiter
        sudo sed -i -e "s#cert_file =.*#cert_file = $SSL_CRT_LOCATION#" $GRAFANA_CONFIG
        sudo sed -i -e "s#cert_key =.*#cert_key = $SSL_KEY_LOCATION#" $GRAFANA_CONFIG
    else
        sudo sed -i -e "s/protocol = http.*/protocol = http/" $GRAFANA_CONFIG
        sudo sed -i -e "s/ssl_mode =.*/ssl_mode = disable/" $GRAFANA_CONFIG
        sudo sed -i -e "s/cert_file =.*/cert_file =/" $GRAFANA_CONFIG
        sudo sed -i -e "s/cert_key =.*/cert_key =/" $GRAFANA_CONFIG
    fi

    echo Done setting up Grafana!
}

###########################################################################
# Install and configure Telegraf - to be run *after* OpenRVDAS is in place!
function install_telegraf {
    echo "#####################################################################"
    echo Installing Telegraf...

    if [ $OS_TYPE == 'MacOS' ]; then
        TELEGRAF_CONF_FILE=telegraf.conf
        TELEGRAF_CONF_DIR=/usr/local/etc/
        TELEGRAF_BIN=/usr/local/bin/telegraf

        brew update
        brew upgrade
        brew install --overwrite telegraf

    # If we're on CentOS
    elif [ $OS_TYPE == 'CentOS' ]; then
        TELEGRAF_CONF_FILE=openrvdas.conf
        TELEGRAF_CONF_DIR=/etc/telegraf/telegraf.d
        TELEGRAF_BIN=/usr/bin/telegraf

        # Remove old repo, if it's lying around
        if [ -e /etc/yum.repos.d/influxdb.repo ]; then
            sudo rm /etc/yum.repos.d/influxdb.repo
        fi
        # From: https://portal.influxdata.com/downloads/
        # influxdata-archive_compat.key GPG fingerprint:
        #     9D53 9D90 D332 8DC7 D6C8 D3B9 D8FF 8E1F 7DF8 B07E
        cat <<EOF | sudo tee /etc/yum.repos.d/influxdata.repo
[influxdata]
name = InfluxData Repository - Stable
baseurl = https://repos.influxdata.com/stable/\$basearch/main
enabled = 1
gpgcheck = 1
gpgkey = https://repos.influxdata.com/influxdata-archive_compat.key
EOF
        sudo yum install -y telegraf

    # If we're on Ubuntu
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        TELEGRAF_CONF_FILE=openrvdas.conf
        TELEGRAF_CONF_DIR=/etc/telegraf/telegraf.d
        TELEGRAF_BIN=/usr/bin/telegraf

        wget -q https://repos.influxdata.com/influxdata-archive_compat.key
        echo '23a1c8836f0afc5ed24e0486339d7cc8f6790b83886c4c96995b88a061c5bb5d influxdata-archive_compat.key' | sha256sum -c && cat influxdata-archive_compat.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/influxdb.gpg > /dev/null
        echo 'deb [signed-by=/etc/apt/trusted.gpg.d/influxdb.gpg] https://repos.influxdata.com/debian stable main' | sudo tee /etc/apt/sources.list.d/influxdata.list

        sudo apt-get update
        sudo apt-get install telegraf
    fi

    # Make sure we've got an InfluxDB auth token
    get_influxdb_auth_token

    # Create conf in /tmp, then move into place, to get around permission quirk
    echo Configuring Telegraf

    TELEGRAF_CONF=$TELEGRAF_CONF_DIR/$TELEGRAF_CONF_FILE

    # For now, don't verify certificates
    if [[ $USE_SSL == 'yes' ]];then
        TELEGRAF_PROTOCOL='https'
        INSECURE_SKIP_VERIFY='insecure_skip_verify = true'
    else
        TELEGRAF_PROTOCOL='http'
        INSECURE_SKIP_VERIFY=''
    fi

    sudo cat > /tmp/$TELEGRAF_CONF_FILE <<EOF
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
[[inputs.net]]
[[inputs.processes]]
[[inputs.swap]]
[[inputs.system]]

[[outputs.influxdb_v2]]
   urls = ["$TELEGRAF_PROTOCOL://127.0.0.1:8086"]
   token = "$INFLUXDB_AUTH_TOKEN"  # Token for authentication.
   organization = "$INFLUXDB_ORGANIZATION"  # InfluxDB organization to write to
   bucket = "_monitoring"  # Destination bucket to write into.
   $INSECURE_SKIP_VERIFY
EOF

    sudo cp /tmp/$TELEGRAF_CONF_FILE $TELEGRAF_CONF
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
    if [[ $INSTALL_INFLUXDB == 'yes' ]]; then
        INSTALLED_PROGRAMS=influxdb

        if [[ $RUN_INFLUXDB == 'yes' ]];then
            AUTOSTART_INFLUXDB=true
        else
            AUTOSTART_INFLUXDB=false
        fi

        if [[ $USE_SSL == 'yes' ]];then
            INFLUX_SSL_OPTIONS="--tls-cert=\"$SSL_CRT_LOCATION\" --tls-key=\"$SSL_KEY_LOCATION\""
        else
            INFLUX_SSL_OPTIONS=""
        fi
        cat >> $TMP_SUPERVISOR_FILE <<EOF
; Run InfluxDB
[program:influxdb]
command=${INFLUX_PATH}/influxd --reporting-disabled $INFLUX_SSL_OPTIONS
directory=${INSTALL_ROOT}/openrvdas
;environment=INFLUXD_CONFIG_PATH=/etc/influxdb
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
    if [[  $INSTALL_GRAFANA == 'yes' ]]; then
        if [[ -z "$INSTALLED_PROGRAMS" ]];then
            INSTALLED_PROGRAMS=grafana
        else
            INSTALLED_PROGRAMS=${INSTALLED_PROGRAMS},grafana
        fi

        if [[ $RUN_GRAFANA == 'yes' ]];then
            AUTOSTART_GRAFANA=true
        else
            AUTOSTART_GRAFANA=false
        fi

        cat >> $TMP_SUPERVISOR_FILE <<EOF

; Run Grafana
[program:grafana]
command=${GRAFANA_PATH}/grafana-server --homepath $GRAFANA_HOMEPATH
directory=$GRAFANA_HOMEPATH
autostart=$AUTOSTART_GRAFANA
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/grafana.stderr
;user=$USER
EOF
    fi

    ##########
    # If Telegraf is installed, create an entry for it.
    if [[  $INSTALL_TELEGRAF == 'yes' ]]; then
        if [[ -z "$INSTALLED_PROGRAMS" ]];then
            INSTALLED_PROGRAMS=telegraf
        else
            INSTALLED_PROGRAMS=${INSTALLED_PROGRAMS},telegraf
        fi

        if [[ $RUN_TELEGRAF == 'yes' ]];then
            AUTOSTART_TELEGRAF=true
        else
            AUTOSTART_TELEGRAF=false
        fi
        cat >> $TMP_SUPERVISOR_FILE <<EOF

; Run Telegraf
[program:telegraf]
command=${TELEGRAF_BIN} --config=${TELEGRAF_CONF}
directory=${INSTALL_ROOT}/openrvdas
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
    sudo supervisorctl reload
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
  yes_no "Would you like to create a non-root user and switch to that uid? " 'yes'
  CREATE_RVDAS_USER=$YES_NO_RESULT
  if [ "$CREATE_RVDAS_USER" == "yes" ]; then
    if [ $OS_TYPE == 'MacOS' ]; then
      echo "Alas, on MacOS, we can't create a user via this script. Please create"
      echo "or switch to another user, then re-run this script under that UID."
      exit_gracefully
    # If we're on Linux
    elif [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
      read -p "OpenRVDAS user to create? ($DEFAULT_RVDAS_USER) " RVDAS_USER
    fi
    RVDAS_USER=${RVDAS_USER:-$DEFAULT_RVDAS_USER}
    create_user $RVDAS_USER
    echo "Switching UID to $RVDAS_USER"
    sudo -u "$target_user" -E bash -c "echo \"Effective UID: $(id -u)\""
    echo "##############################"
    echo "NEW USER: " `whoami`
    echo "##############################"
  else
    exit_gracefully
  fi
fi

# Set creation mask so that everything we install is, by default,
# world readable/executable.
umask 022

echo "#####################################################################"
echo InfluxDB/Grafana/Telegraf configuration script
echo
echo "Will this be a standalone installation? (yes = OpenRVDAS is not installed"
echo "on this machine, no = OpenRVDAS is/will be run on this machine)"
yes_no "Standalone installation? " $DEFAULT_STANDALONE_INSTALLATION
STANDALONE_INSTALLATION=$YES_NO_RESULT

echo "#####################################################################"
read -p "Path to openrvdas directory? ($DEFAULT_INSTALL_ROOT) " INSTALL_ROOT
INSTALL_ROOT=${INSTALL_ROOT:-$DEFAULT_INSTALL_ROOT}
#echo "Activating virtual environment in '${INSTALL_ROOT}/openrvdas'"
#source $INSTALL_ROOT/openrvdas/venv/bin/activate
echo
echo "#####################################################################"
echo "InfluxDB and Grafana can use SSL via secure websockets for off-server"
echo "access to web console and display widgets. If you enable SSL, you will"
echo "need to either have or create SSL .key and .crt files."
echo
echo "If you create a self-signed certificate, users may need to take additional"
echo "steps to connect to the web console and display widgets from their machines'"
echo "browsers. For guidance on this, please see the secure_websockets.md doc in"
echo "this project's docs subdirectory."
echo
yes_no "Use SSL and secure websockets? " $DEFAULT_USE_SSL
USE_SSL=$YES_NO_RESULT

if [ "$USE_SSL" == "yes" ]; then
    # Get or create SSL keys
    echo
    echo "#####################################################################"
    echo "The OpenRVDAS console, cached data server and display widgets use HTTPS"
    echo "and WSS \(secure websockets\) for communication and require an SSL"
    echo "certificate in the form of .key and .crt files. If you already have such"
    echo "keys on your machine that you wish to use, answer "yes" to the question"
    echo "below, and you will be prompted for their locations. Otherwise answer \"no\""
    echo "and you will be prompted to create a self-signed certificate."
    echo
    yes_no "Do you already have a .key and a .crt file to use for this server? " $DEFAULT_HAVE_SSL_CERTIFICATE
    HAVE_SSL_CERTIFICATE=$YES_NO_RESULT
    if [ $HAVE_SSL_CERTIFICATE == 'yes' ]; then
        read -p "Path and name of .crt file? ($DEFAULT_SSL_CRT_LOCATION) " SSL_CRT_LOCATION
        read -p "Path and name of .key file? ($DEFAULT_SSL_KEY_LOCATION) " SSL_KEY_LOCATION
    else
        read -p "Path and name of .crt file to create? ($DEFAULT_SSL_CRT_LOCATION) " SSL_CRT_LOCATION
        read -p "Path and name of .key file to create? ($DEFAULT_SSL_KEY_LOCATION) " SSL_KEY_LOCATION
    fi
    SSL_CRT_LOCATION=${SSL_CRT_LOCATION:-$DEFAULT_SSL_CRT_LOCATION}
    SSL_KEY_LOCATION=${SSL_KEY_LOCATION:-$DEFAULT_SSL_KEY_LOCATION}
else
    # Propagate unused variables so they're saved in defaults
    HAVE_SSL_CERTIFICATE=$DEFAULT_HAVE_SSL_CERTIFICATE
    SSL_CRT_LOCATION=$DEFAULT_SSL_CRT_LOCATION
    SSL_KEY_LOCATION=$DEFAULT_SSL_KEY_LOCATION
fi

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

#########################################################################
#########################################################################
# Create new self-signed SSL certificate, if that's what they want
if [ $USE_SSL == "yes" ] && [ $HAVE_SSL_CERTIFICATE == 'no' ]; then
    echo
    echo "#####################################################################"
    echo "Ready to set up new self-signed SSL certificate."
    setup_ssl_certificate
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

echo
read -p "'Organization' to use for InfluxDB OpenRVDAS data? ($DEFAULT_INFLUXDB_ORGANIZATION) " INFLUXDB_ORGANIZATION
INFLUXDB_ORGANIZATION=${INFLUXDB_ORGANIZATION:-$DEFAULT_INFLUXDB_ORGANIZATION}
echo
read -p "Bucket to use for InfluxDB OpenRVDAS data? ($DEFAULT_INFLUXDB_BUCKET) " INFLUXDB_BUCKET
INFLUXDB_BUCKET=${INFLUXDB_BUCKET:-$DEFAULT_INFLUXDB_BUCKET}

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
sudo supervisorctl stop all || echo "Supervisor not running."

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
