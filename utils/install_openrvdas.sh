#!/bin/bash -e

# OpenRVDAS is available as open source under the MIT License at
#   https:/github.com/oceandatatools/openrvdas
#
# This script installs and configures OpenRVDAS to run.  It
# is designed to be run as root. It should take a (relatively) clean
# Linux/MacOS installation and install and configure all the components
# to run the full OpenRVDAS system.
#
# It should be re-run whenever the code has been refresh. Preferably
# by first running 'git pull' to get the latest copy of the script,
# and then running 'utils/build_openrvdas_centos7.sh' to run that
# script.
#
# The script has been designed to be idempotent, that is, if can be
# run over again with no ill effects.
#
# If you have selected "yes" to running OpenRVDAS as a service then,
# once this script has completed, you should be able to point a
# browser to http://[hostname] and see the OpenRVDAS control
# console.
#
# If you selected "no" when asked whether to run OpenRVDAS as a
# service on boot, you will need to manually start the servers:
#
#   supervisorctl start all
#
# Regardless, running
#
#   supervisorctl status
#
# should show you which services are running.
#
# This script has been tested on a variety of architectures and operating
# systems, but not exhaustively. Bug reports, and even better, bug
# fixes, will be greatly appreciated.

PREFERENCES_FILE='.install_openrvdas_preferences'

# Define this here, even though it's just for MacOS, so that it's defined
# when it's referenced down in install_packages, and doesn't have to
# be defined twice.

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
function get_os_type {
    if [[ `uname -s` == 'Darwin' ]];then
        OS_TYPE=MacOS
        OS_VERSION=`uname -p`
        if [[ $HARDWARE_VERSION == 'arm' ]];then
            echo
            echo "WARNING: detected MacOS ARM architecture. Will install Rosetta emulator and"
            echo "rerun this script emulating X86 architecture."
            echo
            read -p "Hit return to continue or Ctrl-C to exit. " DUMMY_VAR
            echo
            softwareupdate --install-rosetta --agree-to-license

            # Recursively run this script, but now as X86_64
            THIS_SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
            arch -x86_64 /bin/bash $THIS_SCRIPT_PATH

            # Exit quietly after recursive run
            return -1 2> /dev/null || exit -1  # exit correctly if sourced/bashed
        fi

    elif [[ `uname -s` == 'Linux' ]];then
        if [[ ! -z `grep "NAME=\"Ubuntu\"" /etc/os-release` ]];then
            OS_TYPE=Ubuntu
            if [[ ! -z `grep "VERSION_ID=\"18" /etc/os-release` ]];then
                OS_VERSION=18
            elif [[ ! -z `grep "VERSION_ID=\"20" /etc/os-release` ]];then
                OS_VERSION=20
            elif [[ ! -z `grep "VERSION_ID=\"21" /etc/os-release` ]];then
                OS_VERSION=21
            elif [[ ! -z `grep "VERSION_ID=\"22" /etc/os-release` ]];then
                OS_VERSION=22
            elif [[ ! -z `grep "VERSION_ID=\"23" /etc/os-release` ]];then
                OS_VERSION=23
            else
                echo "Sorry - unknown Ubuntu OS Version! - exiting."
                exit_gracefully
            fi

        # With Debian (Raspbian) we're mapping to Ubuntu. Not clear that
        # version 10 -> 18 is the right map, but 11 (bullseye)-> 20 seems to work
        elif [[ ! -z `grep "NAME=\"Debian" /etc/os-release` ]] || [[ ! -z `grep "NAME=\"Raspbian" /etc/os-release` ]];then
            OS_TYPE=Ubuntu
            if [[ ! -z `grep "VERSION_ID=\"10" /etc/os-release` ]];then
                OS_VERSION=18
            elif [[ ! -z `grep "VERSION_ID=\"11" /etc/os-release` ]];then
                OS_VERSION=20
            elif [[ ! -z `grep "VERSION_ID=\"12" /etc/os-release` ]];then
                OS_VERSION=22
            else
                echo "Sorry - unknown Debian OS Version! - exiting."
                exit_gracefully
            fi

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
            echo "Sorry - unknown Linux variant!"
            exit_gracefully
        fi
    else
        echo Unknown OS type: `uname -s`
        exit_gracefully
    fi
}

###########################################################################
###########################################################################
# Read any pre-saved default variables from file
function set_default_variables {
    # Defaults that will be overwritten by the preferences file, if it
    # exists.
    DEFAULT_HOSTNAME=$HOSTNAME
    DEFAULT_INSTALL_ROOT=/opt
    #DEFAULT_HTTP_PROXY=proxy.lmg.usap.gov:3128 #$HTTP_PROXY
    DEFAULT_HTTP_PROXY=$http_proxy

    DEFAULT_OPENRVDAS_REPO=https://github.com/oceandatatools/openrvdas
    DEFAULT_OPENRVDAS_BRANCH=master

    DEFAULT_NONSSL_SERVER_PORT=80
    DEFAULT_SSL_SERVER_PORT=443

    DEFAULT_USE_SSL=no
    DEFAULT_HAVE_SSL_CERTIFICATE=no
    DEFAULT_SSL_CRT_LOCATION=
    DEFAULT_SSL_KEY_LOCATION=

    DEFAULT_RVDAS_USER=rvdas

    DEFAULT_INSTALL_FIREWALLD=no
    DEFAULT_OPENRVDAS_AUTOSTART=yes

    DEFAULT_INSTALL_SIMULATE_NBP=no
    DEFAULT_RUN_SIMULATE_NBP=no

    DEFAULT_INSTALL_GUI=yes

    DEFAULT_SUPERVISORD_WEBINTERFACE=no
    DEFAULT_SUPERVISORD_WEBINTERFACE_AUTH=no
    DEFAULT_SUPERVISORD_WEBINTERFACE_PORT=9001

    DEFAULT_INSTALL_DOC_MARKDOWN=no

    # Read in the preferences file, if it exists, to overwrite the defaults.
    if [ -e $PREFERENCES_FILE ]; then
        echo "#####################################################################"
        echo Reading pre-saved defaults from "$PREFERENCES_FILE"
        source $PREFERENCES_FILE
    fi
}

###########################################################################
###########################################################################
# Save defaults in a preferences file for the next time we run.
function save_default_variables {
    cat > $PREFERENCES_FILE <<EOF
# Defaults written by/to be read by install_openrvdas.sh

DEFAULT_HOSTNAME=$HOSTNAME
DEFAULT_INSTALL_ROOT=$INSTALL_ROOT

#DEFAULT_HTTP_PROXY=proxy.lmg.usap.gov:3128 #$HTTP_PROXY
DEFAULT_HTTP_PROXY=$HTTP_PROXY

DEFAULT_OPENRVDAS_REPO=$OPENRVDAS_REPO
DEFAULT_OPENRVDAS_BRANCH=$OPENRVDAS_BRANCH

DEFAULT_NONSSL_SERVER_PORT=$NONSSL_SERVER_PORT
DEFAULT_SSL_SERVER_PORT=$SSL_SERVER_PORT

DEFAULT_USE_SSL=$USE_SSL
DEFAULT_HAVE_SSL_CERTIFICATE=$HAVE_SSL_CERTIFICATE
DEFAULT_SSL_CRT_LOCATION=$SSL_CRT_LOCATION
DEFAULT_SSL_KEY_LOCATION=$SSL_KEY_LOCATION

DEFAULT_RVDAS_USER=$RVDAS_USER

DEFAULT_INSTALL_FIREWALLD=$INSTALL_FIREWALLD
DEFAULT_OPENRVDAS_AUTOSTART=$OPENRVDAS_AUTOSTART

DEFAULT_INSTALL_GUI=$INSTALL_GUI

DEFAULT_INSTALL_SIMULATE_NBP=$INSTALL_SIMULATE_NBP
DEFAULT_RUN_SIMULATE_NBP=$RUN_SIMULATE_NBP

DEFAULT_SUPERVISORD_WEBINTERFACE=$SUPERVISORD_WEBINTERFACE
DEFAULT_SUPERVISORD_WEBINTERFACE_AUTH=$SUPERVISORD_WEBINTERFACE_AUTH
DEFAULT_SUPERVISORD_WEBINTERFACE_PORT=$SUPERVISORD_WEBINTERFACE_PORT

DEFAULT_INSTALL_DOC_MARKDOWN=$INSTALL_DOC_MARKDOWN
EOF
}

###########################################################################
###########################################################################
# Set hostname
function set_hostname {
    HOSTNAME=$1

    # If we're on MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        echo Not changing hostname on MacOS
        #sudo scutil --set HostName $HOSTNAME
        #sudo scutil --set LocalHostName $HOSTNAME
        #sudo scutil --set ComputerName $HOSTNAME
        #dscacheutil -flushcache

    # If we're on CentOS/RHEL
    elif [ $OS_TYPE == 'CentOS' ]; then
        sudo hostnamectl set-hostname $HOSTNAME
        sudo echo "HOSTNAME=$HOSTNAME" > /etc/sysconfig/network  || echo "Unable to update /etc/sysconfig/network"

    # Ubuntu/Debian
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        sudo hostnamectl set-hostname $HOSTNAME
        sudo echo $HOSTNAME > /etc/hostname || echo "Unable to update /etc/hostname"
    fi

    ETC_HOSTS_LINE="127.0.1.1	$HOSTNAME"
    if grep -q "$ETC_HOSTS_LINE" /etc/hosts ; then
        echo Hostname already in /etc/hosts
    else
        echo Skipping adding to /etc/hosts
        sudo echo "$ETC_HOSTS_LINE" >> /etc/hosts || echo "Unable to update /etc/hosts"
    fi
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
        sudo yum install -y epel-release
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

        if [ $OS_VERSION == '7' ]; then
            # Build Python, too, if we don't have right version
            PYTHON_VERSION='3.8.3'
            if [ "`/usr/local/bin/python3 --version`" == "Python $PYTHON_VERSION" ]; then
                echo Already have appropriate version of Python3
            else
                cd /var/tmp
                PYTHON_BASE=Python-${PYTHON_VERSION}
                PYTHON_TGZ=${PYTHON_BASE}.tgz
                [ -e $PYTHON_TGZ ] || wget https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_TGZ}
                tar xvf ${PYTHON_TGZ}
                cd ${PYTHON_BASE}
                sh ./configure # --enable-optimizations
                sudo make altinstall

                sudo ln -s -f /usr/local/bin/python3.8 /usr/local/bin/python3
                sudo ln -s -f /usr/local/bin/pip3.8 /usr/local/bin/pip3
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
# Set up Python packages
function setup_python_packages {
    # Expect the following shell variables to be appropriately set:
    # INSTALL_ROOT - path where openrvdas/ is

    # Set up virtual environment
    VENV_PATH=$INSTALL_ROOT/openrvdas/venv

    ## Bit of a challenge here - if our new install has a newer version of
    ## Python or something, reusing the existing venv can cause subtle
    ## havoc. But deleting and rebuilding it each time is a mess. Commenting
    ## out the delete for now...
    ##
    # We'll rebuild the virtual environment each time to avoid version skew
    #if [ -d $VENV_PATH ];then
    #    mv $VENV_PATH ${VENV_PATH}.bak.$$
    #fi

    #if [ -e '${HOMEBREW_BASE}/bin/python3' ];then
    #    eval "$(${HOMEBREW_BASE}/bin/brew shellenv)"
    #    PYTHON_PATH=${HOMEBREW_BASE}/bin/python3
    #elif [ -e '/usr/local/bin/python3' ];then
    #    PYTHON_PATH=/usr/local/bin/python3
    #elif [ -e '/usr/bin/python3' ];then
    #    PYTHON_PATH=/usr/bin/python3
    #else
    #    echo 'No python3 found?!?'
    #    exit_gracefully
    #fi

    echo "Creating virtual environment"
    cd $INSTALL_ROOT/openrvdas
    python3 -m venv $VENV_PATH
    source $VENV_PATH/bin/activate  # activate virtual environment

    echo "Installing Python packages - please enter sudo password if prompted."
    # For some reason, locked down RHEL8 boxes require sudo here, and require
    # us to execute pip via python. Lord love a duck...
    venv/bin/python venv/bin/pip3 install \
      --trusted-host pypi.org --trusted-host files.pythonhosted.org \
      --upgrade pip
    venv/bin/python venv/bin/pip3 install \
      --trusted-host pypi.org --trusted-host files.pythonhosted.org \
      wheel
    venv/bin/python venv/bin/pip3 install -r utils/requirements.txt
}

###########################################################################
###########################################################################
# Set up NGINX
function setup_nginx {

    # CentOS/RHEL or Debian/Ubuntu
    if [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
        # Disable because we're going to run it via supervisor
        systemctl stop nginx
        systemctl disable nginx # NGINX seems to be enabled by default?
    fi

    if [ "$USE_SSL" == "yes" ]; then
        SERVER_PROTOCOL='ssl'
        SSL_COMMENT=''   # don't comment out SSL stuff
    else
        SERVER_PROTOCOL='default_server'
        SSL_COMMENT='#'   # do comment out SSL stuff

    fi

    if [ $INSTALL_DOC_MARKDOWN == 'yes' ];then
        MARKDOWN_COMMENT='' # We uncomment the Strapdown-related lines in conf
    else
        MARKDOWN_COMMENT='#'
    fi

    # Now create the nginx conf file in place and link it up
    cat > $INSTALL_ROOT/openrvdas/django_gui/openrvdas_nginx.conf<<EOF
# openrvdas_nginx.conf

worker_processes  auto;
events {
    worker_connections  1024;
}

http {
    #include       mime.types;
    default_type  application/octet-stream;

    #log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
    #                  '$status $body_bytes_sent "$http_referer" '
    #                  '"$http_user_agent" "$http_x_forwarded_for"';

    #access_log  logs/access.log  main;

    sendfile        on;
    #tcp_nopush     on;
    keepalive_timeout  65;

    # the upstream component nginx needs to connect to
    upstream django {
        server unix://${INSTALL_ROOT}/openrvdas/django_gui/openrvdas.sock; # for a file socket
    }

    # OpenRVDAS HTTPS server
    server {
        # the port your site will be served on; typically 443
        listen      *:${SERVER_PORT} ${SERVER_PROTOCOL};
        server_name _; # accept any host name
        charset     utf-8;

        # Section will be commented out if we're not using SSL
        ${SSL_COMMENT}ssl_certificate     $SSL_CRT_LOCATION;
        ${SSL_COMMENT}ssl_certificate_key $SSL_KEY_LOCATION;
        ${SSL_COMMENT}ssl_protocols       TLSv1 TLSv1.1 TLSv1.2;
        ${SSL_COMMENT}ssl_ciphers         HIGH:!aNULL:!MD5;

        # max upload size
        client_max_body_size 75M;   # adjust to taste

        # Django media
        location /media  {
            alias ${INSTALL_ROOT}/openrvdas/media;  # project media files
        }

        location /display {
            alias ${INSTALL_ROOT}/openrvdas/display/html; # display pages
            autoindex on;
        }
        location /js {
            alias /${INSTALL_ROOT}/openrvdas/display/js; # display pages
            default_type application/javascript;
        }
        location /css {
            alias /${INSTALL_ROOT}/openrvdas/display/css; # display pages
            default_type text/css;
        }
        location /static {
            alias ${INSTALL_ROOT}/openrvdas/static; # project static files
            autoindex on;
        }
        location /docs {
            alias ${INSTALL_ROOT}/openrvdas/docs; # project doc files
            autoindex on;
        }
        # Added by KPed so Markdown renders in the browser
        # See https://gist.github.com/shukebeta/b7435d02892cb2ad2b9c8d56572adb2b
        ${MARKDOWN_COMMENT}location ~ /.*\.md {
        ${MARKDOWN_COMMENT}    root /opt/openrvdas;
        ${MARKDOWN_COMMENT}    default_type text/html;
        ${MARKDOWN_COMMENT}    charset UTF-8;
        ${MARKDOWN_COMMENT}    add_before_body /static/StrapDown.js/prepend;
        ${MARKDOWN_COMMENT}    add_after_body /static/StrapDown.js/postpend;
        ${MARKDOWN_COMMENT}}

        # Internally, Cached Data Server operates on port 8766; we proxy
        # it externally, serve cached data server at $SERVER_PORT/cds-ws
        location /cds-ws {
            proxy_pass http://localhost:8766;
            proxy_http_version 1.1;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection "Upgrade";
            proxy_set_header Host \$host;
        }

        # Finally, send all non-CDS, non-media requests to the Django server.
        location / {
            uwsgi_pass  django;
            include     ${INSTALL_ROOT}/openrvdas/django_gui/uwsgi_params;
        }
    }
}
EOF

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

###########################################################################
###########################################################################
# Set up Django
function setup_django {
    # Expect the following shell variables to be appropriately set:
    # RVDAS_USER - valid userid
    # RVDAS_DATABASE_PASSWORD - string to use for Django password

    cd ${INSTALL_ROOT}/openrvdas
    source ${INSTALL_ROOT}/openrvdas/venv/bin/activate
    cp django_gui/settings.py.dist django_gui/settings.py
    sed -i -e "s/WEBSOCKET_PROTOCOL = 'ws'/WEBSOCKET_PROTOCOL = '${WEBSOCKET_PROTOCOL}'/g" django_gui/settings.py
    sed -i -e "s/WEBSOCKET_PORT = 80/WEBSOCKET_PORT = ${SERVER_PORT}/g" django_gui/settings.py
    sed -i -e "s/'USER': 'rvdas'/'USER': '${RVDAS_USER}'/g" django_gui/settings.py
    sed -i -e "s/'PASSWORD': 'rvdas'/'PASSWORD': '${RVDAS_DATABASE_PASSWORD}'/g" django_gui/settings.py

    # NOTE: we're still inside virtualenv, so we're getting the python
    # that was installed under it.
    python3 manage.py makemigrations django_gui
    python3 manage.py migrate
    rm -rf static
    python3 manage.py collectstatic --no-input --clear --link -v 0
    chmod -R og+rX static

    # A temporary hack to allow the display/ pages to be accessed by Django
    # in their old location of static/widgets/
    cd static;ln -s html widgets;cd ..

    # Bass-ackwards way of creating superuser $RVDAS_USER, as the
    # createsuperuser command won't work from a script
    python3 manage.py shell <<EOF
from django.contrib.auth.models import User
try:
  User.objects.get(username='${RVDAS_USER}').delete()
except User.DoesNotExist:
  pass

User.objects.create_superuser('${RVDAS_USER}',
                              '${RVDAS_USER}@example.com',
                              '${RVDAS_DATABASE_PASSWORD}')
EOF
}

###########################################################################
###########################################################################
# Set up UWSGI
function setup_uwsgi {
    # Expect the following shell variables to be appropriately set:
    # HOSTNAME - name of host
    # INSTALL_ROOT - path where openrvdas/ is

    # MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        ETC_HOME=/usr/local/etc

    # CentOS/RHEL and Ubuntu/Debian
    elif [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
        ETC_HOME=/etc
    fi
    cp $ETC_HOME/nginx/uwsgi_params $INSTALL_ROOT/openrvdas/django_gui

    cat > ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_uwsgi.ini <<EOF
# openrvdas_uwsgi.ini file
[uwsgi]

# Django-related settings
# the base directory (full path)
chdir           = ${INSTALL_ROOT}/openrvdas
# Django's wsgi file
module          = django_gui.wsgi
# Where to find bin/python
home            = ${INSTALL_ROOT}/openrvdas/venv

# process-related settings
# master
master          = true
# maximum number of worker processes
processes       = 10
# the socket (use the full path to be safe
socket          = ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas.sock
# ... with appropriate permissions - may be needed
# chmod-socket    = 664
chmod-socket    = 666
# clear environment on exit
vacuum          = true
EOF

    # Make vassal directory and copy symlink in
    [ -e $ETC_HOME/uwsgi/vassals ] || mkdir -p $ETC_HOME/uwsgi/vassals
    sudo ln -sf ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_uwsgi.ini \
          $ETC_HOME/uwsgi/vassals/
}

###########################################################################
###########################################################################
# Set up supervisord files
function setup_supervisor {
    # Expect the following shell variables to be appropriately set:
    # RVDAS_USER - valid username
    # INSTALL_ROOT - path where openrvdas/ is found
    # OPENRVDAS_AUTOSTART - 'true' if we're to autostart, else 'false'

    # If we're not installing the web GUI, comment out those bits of
    # the supervisor config that run them.
    if [[ "$INSTALL_GUI" == "yes" ]];then
        GUI_COMMENT=''
    else
        GUI_COMMENT=';'
    fi

    VENV_BIN=${INSTALL_ROOT}/openrvdas/venv/bin
    if [ $OPENRVDAS_AUTOSTART = 'yes' ]; then
        AUTOSTART=true
    else
        AUTOSTART=false
    fi

    # Whether the simulation script is commented out, and if not,
    # whether it should autorun on boot
    SIMULATE_NBP_COMMENT=';'
    AUTOSTART_SIMULATE_NBP='false'
    if [ $INSTALL_SIMULATE_NBP = 'yes' ]; then
        SIMULATE_NBP_COMMENT=''
    fi
    if [ $RUN_SIMULATE_NBP = 'yes' ]; then
        AUTOSTART_SIMULATE_NBP='true'
    fi

    # MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        ETC_HOME=/usr/local/etc
        HTTP_HOST=127.0.0.1
        NGINX_BIN=/usr/local/bin/nginx
        SUPERVISOR_DIR=/usr/local/etc/supervisor.d/
        SUPERVISOR_SUFFIX='ini'
        SUPERVISOR_SOCK=/usr/local/var/run/supervisor.sock
        COMMENT_SOCK_OWNER=';'

    # CentOS/RHEL
    elif [ $OS_TYPE == 'CentOS' ]; then
        ETC_HOME=/etc
        HTTP_HOST='*'
        NGINX_BIN=/usr/sbin/nginx
        SUPERVISOR_DIR=/etc/supervisord.d
        SUPERVISOR_SUFFIX='ini'
        SUPERVISOR_SOCK=/var/run/supervisor/supervisor.sock
        COMMENT_SOCK_OWNER=''

    # Ubuntu/Debian
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        ETC_HOME=/etc
        HTTP_HOST='*'
        NGINX_BIN=/usr/sbin/nginx
        SUPERVISOR_DIR=/etc/supervisor/conf.d
        SUPERVISOR_SUFFIX='conf'
        SUPERVISOR_SOCK=/var/run/supervisor.sock
        COMMENT_SOCK_OWNER=''
    fi

    SUPERVISOR_FILE=$SUPERVISOR_DIR/openrvdas.${SUPERVISOR_SUFFIX}
    LOGGER_MANAGER_FILE=$SUPERVISOR_DIR/openrvdas_logger_manager.${SUPERVISOR_SUFFIX}
    CACHED_DATA_FILE=$SUPERVISOR_DIR/openrvdas_cached_data.${SUPERVISOR_SUFFIX}
    DJANGO_FILE=$SUPERVISOR_DIR/openrvdas_django.${SUPERVISOR_SUFFIX}
    SIMULATE_FILE=$SUPERVISOR_DIR/openrvdas_simulate.${SUPERVISOR_SUFFIX}

    sudo mkdir -p $SUPERVISOR_DIR

    #######################################################
    # Write out the overall supervisor file, filling in variables
    TEMP_FILE=/tmp/openrvdas_tmp.ini
    sudo rm $TEMP_FILE

    cat > $TEMP_FILE <<EOF
; First, override the default socket permissions to allow user
; $RVDAS_USER to run supervisorctl
[unix_http_server]
file=$SUPERVISOR_SOCK   ; (the path to the socket file)
chmod=0770              ; socket file mode (default 0700)
${COMMENT_SOCK_OWNER}chown=nobody:${RVDAS_GROUP}
EOF

    if [ $SUPERVISORD_WEBINTERFACE == 'yes' ]; then
        cat >> $TEMP_FILE <<EOF

[inet_http_server]
port=${SUPERVISORD_WEBINTERFACE_PORT}
EOF
        if [ $SUPERVISORD_WEBINTERFACE_AUTH == 'yes' ]; then
            SUPERVISORD_WEBINTERFACE_HASH=`echo -n ${SUPERVISORD_WEBINTERFACE_PASS} | sha1sum | awk '{printf("{SHA}%s",$1)}'`
            cat >> $TEMP_FILE <<EOF
username=${SUPERVISORD_WEBINTERFACE_USER}
password=${SUPERVISORD_WEBINTERFACE_HASH} ; echo -n "<password>" | sha1sum | awk '{printf("{SHA}%s",\$1)}'
EOF
        fi
    fi
    sudo mv $TEMP_FILE $SUPERVISOR_FILE

    #######################################################
    # Write out the Logger Manager file
    cat > $TEMP_FILE <<EOF
; Supervisor configurations for LoggerManager
[program:logger_manager]
command=${VENV_BIN}/python server/logger_manager.py --database django --data_server_websocket :8766 -v -V --no-console
environment=PATH="${VENV_BIN}:/usr/bin:/usr/local/bin"
directory=${INSTALL_ROOT}/openrvdas
autostart=$AUTOSTART
autorestart=true
startretries=3
killasgroup=true
stderr_logfile=/var/log/openrvdas/logger_manager.stderr
stderr_logfile_maxbytes=10000000 ; 10M
stderr_logfile_maxbackups=100
user=$RVDAS_USER
EOF
    sudo mv $TEMP_FILE $LOGGER_MANAGER_FILE

    #######################################################
    # Write out the Cached Data Server file
    cat > $TEMP_FILE <<EOF
; Supervisor configurations for LoggerManager and CachedDataServer
[program:cached_data_server]
command=${VENV_BIN}/python server/cached_data_server.py --port 8766 --disk_cache /var/tmp/openrvdas/disk_cache --max_records 8640 -v
directory=${INSTALL_ROOT}/openrvdas
autostart=$AUTOSTART
autorestart=true
startretries=3
killasgroup=true
stderr_logfile=/var/log/openrvdas/cached_data_server.stderr
stderr_logfile_maxbytes=10000000 ; 10M
stderr_logfile_maxbackups=100
user=$RVDAS_USER
EOF
    sudo mv $TEMP_FILE $CACHED_DATA_FILE


    #######################################################
    # Write out the Django GUI files, filling in variables
    cat > $TEMP_FILE <<EOF
; Supervisor configurations for Django GUI
${GUI_COMMENT}[program:nginx]
${GUI_COMMENT}command=${NGINX_BIN} -g 'daemon off;' -c ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_nginx.conf
${GUI_COMMENT}directory=${INSTALL_ROOT}/openrvdas
${GUI_COMMENT}autostart=$AUTOSTART
${GUI_COMMENT}autorestart=true
${GUI_COMMENT}startretries=3
${GUI_COMMENT}killasgroup=true
${GUI_COMMENT}stderr_logfile=/var/log/openrvdas/nginx.stderr
${GUI_COMMENT}stderr_logfile_maxbytes=10000000 ; 10M
${GUI_COMMENT}stderr_logfile_maxbackups=100
${GUI_COMMENT};user=$RVDAS_USER

${GUI_COMMENT}[program:uwsgi]
${GUI_COMMENT}command=${VENV_BIN}/uwsgi ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_uwsgi.ini --thunder-lock --enable-threads
${GUI_COMMENT}stopsignal=INT
${GUI_COMMENT}directory=${INSTALL_ROOT}/openrvdas
${GUI_COMMENT}autostart=$AUTOSTART
${GUI_COMMENT}autorestart=true
${GUI_COMMENT}startretries=3
${GUI_COMMENT}killasgroup=true
${GUI_COMMENT}stderr_logfile=/var/log/openrvdas/uwsgi.stderr
${GUI_COMMENT}stderr_logfile_maxbytes=10000000 ; 10M
${GUI_COMMENT}stderr_logfile_maxbackups=100
${GUI_COMMENT}user=$RVDAS_USER

${GUI_COMMENT}[group:django]
${GUI_COMMENT}programs=nginx,uwsgi
EOF
    sudo mv $TEMP_FILE $DJANGO_FILE

    #######################################################
    # Write out the simulator commands, filling in variables
    cat > $TEMP_FILE <<EOF
; Supervisor configurations for OpenRVDAS data simulator
${SIMULATE_NBP_COMMENT}[program:simulate_nbp]
${SIMULATE_NBP_COMMENT}command=${VENV_BIN}/python logger/utils/simulate_data.py --config test/NBP1406/simulate_NBP1406.yaml
${SIMULATE_NBP_COMMENT}directory=${INSTALL_ROOT}/openrvdas
${SIMULATE_NBP_COMMENT}autostart=${AUTOSTART_SIMULATE_NBP}
${SIMULATE_NBP_COMMENT}autorestart=true
${SIMULATE_NBP_COMMENT}startretries=3
${SIMULATE_NBP_COMMENT}killasgroup=true
${SIMULATE_NBP_COMMENT}stderr_logfile=/var/log/openrvdas/simulate_nbp.stderr
${SIMULATE_NBP_COMMENT}stderr_logfile_maxbytes=10000000 ; 10M
${SIMULATE_NBP_COMMENT}stderr_logfile_maxbackups=100
${SIMULATE_NBP_COMMENT}user=$RVDAS_USER

${SIMULATE_NBP_COMMENT}[group:simulate]
${SIMULATE_NBP_COMMENT}programs=simulate_nbp
EOF
    sudo cp $TEMP_FILE $SIMULATE_FILE
}

###########################################################################
###########################################################################
# CentOS/RHEL ONLY - Set up firewall daemon and open relevant ports
function setup_firewall {
    if [ $OS_TYPE == 'MacOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
        echo "No firewall setup on $OS_TYPE"
        return
    fi

    # All this is CentOS/RHEL only
    yum install -y firewalld
    echo "#####################################################################"
    echo "Setting SELINUX permissions and firewall ports"
    echo "This could take a while..."

    # The old way of enabling things...
    # (sed -i -e 's/SELINUX=enforcing/SELINUX=permissive/g' /etc/selinux/config) || echo UNABLE TO UPDATE SELINUX! Continuing...

    # The new way of more selectively enabling things
    setsebool -P nis_enabled 1
    setsebool -P use_nfs_home_dirs 1
    setsebool -P httpd_can_network_connect 1
    semanage permissive -a httpd_t

    # Set up the firewall and open some holes in it
    systemctl start firewalld
    systemctl enable firewalld

    firewall-cmd -q --set-default-zone=public
    firewall-cmd -q --permanent --add-port=${SERVER_PORT}/tcp > /dev/null

    if [ "$SUPERVISORD_WEBINTERFACE" == 'yes' ]; then
        firewall-cmd -q --permanent --add-port=${SUPERVISORD_WEBINTERFACE_PORT}/tcp > /dev/null
    fi

    if [ ! -z "$TCP_PORTS_TO_OPEN" ]; then
        for PORT in "${TCP_PORTS_TO_OPEN[@]}"
        do
            PORT="$(echo -e "${PORT}" | tr -d '[:space:]')"  # trim whitespace
            echo Opening $PORT/tcp
            firewall-cmd -q --permanent --add-port=$PORT/tcp
        done
    fi

    if [ ! -z "$UDP_PORTS_TO_OPEN" ]; then
        for PORT in "${UDP_PORTS_TO_OPEN[@]}"
        do
            PORT="$(echo -e "${PORT}" | tr -d '[:space:]')"  # trim whitespace
            echo Opening $PORT/udp
            firewall-cmd -q --permanent --add-port=$PORT/udp
        done
    fi

    #firewall-cmd -q --permanent --add-port=80/tcp > /dev/null

    #firewall-cmd -q --permanent --add-port=8001/tcp > /dev/null
    #firewall-cmd -q --permanent --add-port=8002/tcp > /dev/null

    # Supervisord ports - 9001 is default system-wide supervisor
    # and 9002 is the captive supervisor that logger_manager uses.
    #firewall-cmd -q --permanent --add-port=9001/tcp > /dev/null

    # Websocket ports
    #firewall-cmd -q --permanent --add-port=8765/tcp > /dev/null # status
    #firewall-cmd -q --permanent --add-port=8766/tcp > /dev/null # data

    # Our favorite UDP port for network data
    #firewall-cmd -q --permanent --add-port=6224/udp > /dev/null
    #firewall-cmd -q --permanent --add-port=6225/udp > /dev/null

    # For unittest access
    #firewall-cmd -q --permanent --add-port=8000/udp > /dev/null
    #firewall-cmd -q --permanent --add-port=8001/udp > /dev/null
    #firewall-cmd -q --permanent --add-port=8002/udp > /dev/null
    firewall-cmd -q --reload > /dev/null
    echo "Done setting SELINUX permissions"
}


###########################################################################
###########################################################################
# Download and install js script to render .md documents
function setup_markdown {
   # Get the Strapdown.js package that will render .md files
    STRAPDOWN_PATH=${INSTALL_ROOT}/openrvdas/static
    git clone https://github.com/Naereen/StrapDown.js.git $STRAPDOWN_PATH/Strapdown.js
    cat > ${STRAPDOWN_PATH}/Strapdown.js/prepend <<EOF
<!DOCTYPE html>
<html>
<xmp theme='cyborg' style='display:none;'t>
EOF
    cat > ${STRAPDOWN_PATH}/Strapdown.js/postpend <<EOF
<!DOCTYPE html>
</xmp>
<script src='/static/StrapDown.js/strapdown.js'></script>
</html>
EOF
}

###########################################################################
###########################################################################
###########################################################################
###########################################################################
# Start of actual script
###########################################################################
###########################################################################

echo
echo "OpenRVDAS configuration script"

# Read from the preferences file in $PREFERENCES_FILE, if it exists
set_default_variables

# Set OS_TYPE to either MacOS, CentOS or Ubuntu
get_os_type

# Set creation mask so that everything we install is, by default,
# world readable/executable.
umask 022

echo "#####################################################################"
# We don't set hostname on MacOS
if [ $OS_TYPE != 'MacOS' ]; then
    read -p "Name to assign to host ($DEFAULT_HOSTNAME)? " HOSTNAME
    HOSTNAME=${HOSTNAME:-$DEFAULT_HOSTNAME}
    echo "Hostname will be '$HOSTNAME'"
    # Set hostname
    set_hostname $HOSTNAME
fi

read -p "OpenRVDAS install root? ($DEFAULT_INSTALL_ROOT) " INSTALL_ROOT
INSTALL_ROOT=${INSTALL_ROOT:-$DEFAULT_INSTALL_ROOT}
echo "Install root will be '$INSTALL_ROOT'"
echo
read -p "Repository to install from? ($DEFAULT_OPENRVDAS_REPO) " OPENRVDAS_REPO
OPENRVDAS_REPO=${OPENRVDAS_REPO:-$DEFAULT_OPENRVDAS_REPO}

read -p "Repository branch to install? ($DEFAULT_OPENRVDAS_BRANCH) " OPENRVDAS_BRANCH
OPENRVDAS_BRANCH=${OPENRVDAS_BRANCH:-$DEFAULT_OPENRVDAS_BRANCH}

read -p "HTTP/HTTPS proxy to use ($DEFAULT_HTTP_PROXY)? " HTTP_PROXY
HTTP_PROXY=${HTTP_PROXY:-$DEFAULT_HTTP_PROXY}

[ -z $HTTP_PROXY ] || echo Setting up proxy $HTTP_PROXY
[ -z $HTTP_PROXY ] || export http_proxy=$HTTP_PROXY
[ -z $HTTP_PROXY ] || export https_proxy=$HTTP_PROXY

echo
echo "Will install from github.com"
echo "Repository: '$OPENRVDAS_REPO'"
echo "Branch: '$OPENRVDAS_BRANCH'"

# Create user if they don't exist yet on Linux, but MacOS needs to
# user a pre-existing user, because creating a user is a pain.
echo
echo "#####################################################################"
if [ $OS_TYPE == 'MacOS' ]; then
    read -p "Existing user to set system up for? ($DEFAULT_RVDAS_USER) " RVDAS_USER
# If we're on Linux
elif [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
    read -p "OpenRVDAS user to create? ($DEFAULT_RVDAS_USER) " RVDAS_USER
fi
RVDAS_USER=${RVDAS_USER:-$DEFAULT_RVDAS_USER}
create_user $RVDAS_USER

if [ $OS_TYPE == 'MacOS' ]; then
    RVDAS_GROUP=wheel
# If we're on Linux
else
    RVDAS_GROUP=$RVDAS_USER
fi

read -p "Django/database password to use for user $RVDAS_USER? ($RVDAS_USER) " RVDAS_DATABASE_PASSWORD
RVDAS_DATABASE_PASSWORD=${RVDAS_DATABASE_PASSWORD:-$RVDAS_USER}

#########################################################################
#########################################################################
echo
echo "#####################################################################"
echo "OpenRVDAS can use SSL via secure websockets for off-server access to web"
echo "console and display widgets. If you enable SSL, you will need to either"
echo "have or create SSL .key and .crt files."
echo
echo "If you create a self-signed certificate, users may need to take additional"
echo "steps to connect to the web console and display widgets from their machines'"
echo "browsers. For guidance on this, please see the secure_websockets.md doc in"
echo "this project's docs subdirectory."
echo
yes_no "Use SSL and secure websockets? " $DEFAULT_USE_SSL
USE_SSL=$YES_NO_RESULT

if [ "$USE_SSL" == "yes" ]; then
    echo
    read -p "Port on which to serve web console? ($DEFAULT_SSL_SERVER_PORT) " SSL_SERVER_PORT
    SSL_SERVER_PORT=${SSL_SERVER_PORT:-$DEFAULT_SSL_SERVER_PORT}
    SERVER_PORT=$SSL_SERVER_PORT
    WEBSOCKET_PROTOCOL='wss'

    # Propagate unused variables so they're saved in defaults
    NONSSL_SERVER_PORT=$DEFAULT_NONSSL_SERVER_PORT

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
        read -p "Location of .crt file? ($DEFAULT_SSL_CRT_LOCATION) " SSL_CRT_LOCATION
        read -p "Location of .key file? ($DEFAULT_SSL_KEY_LOCATION) " SSL_KEY_LOCATION
    else
        read -p "Where to create .crt file? ($DEFAULT_SSL_CRT_LOCATION) " SSL_CRT_LOCATION
        read -p "Where to create .key file? ($DEFAULT_SSL_KEY_LOCATION) " SSL_KEY_LOCATION
    fi
    SSL_CRT_LOCATION=${SSL_CRT_LOCATION:-$DEFAULT_SSL_CRT_LOCATION}
    SSL_KEY_LOCATION=${SSL_KEY_LOCATION:-$DEFAULT_SSL_KEY_LOCATION}
else
    echo
    read -p "Port on which to serve web console? ($DEFAULT_NONSSL_SERVER_PORT) " NONSSL_SERVER_PORT
    NONSSL_SERVER_PORT=${NONSSL_SERVER_PORT:-$DEFAULT_NONSSL_SERVER_PORT}
    SERVER_PORT=$NONSSL_SERVER_PORT
    WEBSOCKET_PROTOCOL='ws'

    # Propagate unused variables so they're saved in defaults
    SSL_SERVER_PORT=$DEFAULT_SSL_SERVER_PORT
    HAVE_SSL_CERTIFICATE=$DEFAULT_HAVE_SSL_CERTIFICATE
    SSL_CRT_LOCATION=$DEFAULT_SSL_CRT_LOCATION
    SSL_KEY_LOCATION=$DEFAULT_SSL_KEY_LOCATION
fi

#########################################################################
#########################################################################
# CentOS/RHEL only: do they want to install/configure firewalld?
INSTALL_FIREWALLD=no
if [ $OS_TYPE == 'CentOS' ]; then
    echo
    echo "#####################################################################"
    echo "The firewalld daemon can be installed and configured to only allow access"
    echo "to ports used by OpenRVDAS."
    echo
    yes_no "Install and configure firewalld?" $DEFAULT_INSTALL_FIREWALLD
    INSTALL_FIREWALLD=$YES_NO_RESULT

    if [ $INSTALL_FIREWALLD == 'yes' ]; then
        echo "The installation script will open port $SERVER_PORT for TCP console access."
        echo "What other ports should be opened for TCP or UDP? (enter comma-separated"
        echo "list of numbers, or hit return to open no additional ports.)"
        echo
        IFS=',' read -p "Additional TCP ports to open? " -a TCP_PORTS_TO_OPEN
        IFS=',' read -p "Additional UDP ports to open? " -a UDP_PORTS_TO_OPEN
    fi
fi

#########################################################################
#########################################################################
# Start OpenRVDAS as a service?
echo
echo "#####################################################################"
echo "The OpenRVDAS server can be configured to start on boot. If you wish this"
echo "to happen, it will be run/monitored by the supervisord service using the"
echo "configuration file in /etc/supervisord.d/openrvdas.ini."
echo
echo "If you do not wish it to start automatically, it may still be run manually"
echo "from the command line or started via supervisor by running supervisorctl"
echo "and starting processes logger_manager and cached_data_server."
echo
yes_no "Start the OpenRVDAS server on boot? " $DEFAULT_OPENRVDAS_AUTOSTART
OPENRVDAS_AUTOSTART=$YES_NO_RESULT

# Set up simulate_nbp script?
echo
echo "#####################################################################"
echo "For test installations, OpenRVDAS can configure simulated inputs from"
echo "stored data, which will allow you to run the \"NBP1406_cruise.yaml\""
echo "configuration out of the box. This script will be configured to run"
echo "under supervisord as \"simulate:simulate_nbp\"."
echo
yes_no "Do you want to install this script?" $DEFAULT_INSTALL_SIMULATE_NBP
INSTALL_SIMULATE_NBP=$YES_NO_RESULT

if [ $INSTALL_SIMULATE_NBP == 'yes' ]; then
  yes_no "Run simulate:simulate_nbp on boot?" $DEFAULT_RUN_SIMULATE_NBP
  RUN_SIMULATE_NBP=$YES_NO_RESULT
else
  RUN_SIMULATE_NBP=no
fi


#########################################################################
# Install web console programs - nginx and uwsgi?
echo
echo "#####################################################################"
echo "The full OpenRVDAS installation includes a web-based console for loading"
echo "and controlling loggers, but a slimmed-down version of the code may be"
echo "installed and run without it if desired for portability or computational"
echo "reasons."
echo
yes_no "Install OpenRVDAS web console GUI? " $DEFAULT_INSTALL_GUI
INSTALL_GUI=$YES_NO_RESULT

#########################################################################
# Enable Supervisor web-interface?
echo
echo "#####################################################################"
echo "The supervisord service provides an optional web-interface that enables"
echo "operators to start/stop/restart the OpenRVDAS main processes from a web-"
echo "browser."
echo
yes_no "Enable Supervisor Web-interface? " $DEFAULT_SUPERVISORD_WEBINTERFACE
SUPERVISORD_WEBINTERFACE=$YES_NO_RESULT

if [ $SUPERVISORD_WEBINTERFACE == 'yes' ]; then

    read -p "Port on which to serve web interface? ($DEFAULT_SUPERVISORD_WEBINTERFACE_PORT) " SUPERVISORD_WEBINTERFACE_PORT
    SUPERVISORD_WEBINTERFACE_PORT=${SUPERVISORD_WEBINTERFACE_PORT:-$DEFAULT_SUPERVISORD_WEBINTERFACE_PORT}

    echo "Would you like to enable a password on the supervisord web-interface?"
    echo
    yes_no "Enable Supervisor Web-interface user/pass? " $DEFAULT_SUPERVISORD_WEBINTERFACE_AUTH
    SUPERVISORD_WEBINTERFACE_AUTH=$YES_NO_RESULT

    if [ $SUPERVISORD_WEBINTERFACE_AUTH == 'yes' ]; then
        read -p "Username? ($RVDAS_USER) " SUPERVISORD_WEBINTERFACE_USER
        SUPERVISORD_WEBINTERFACE_USER=${SUPERVISORD_WEBINTERFACE_USER:-$RVDAS_USER}

        read -p "Password? ($RVDAS_USER) " SUPERVISORD_WEBINTERFACE_PASS
        SUPERVISORD_WEBINTERFACE_PASS=${SUPERVISORD_WEBINTERFACE_PASS:-$RVDAS_USER}
    fi
fi
echo
echo "#####################################################################"
echo "This script can install Strapdown.js so that the .md files in"
echo "the /docs directory are rendered properly."
echo "under supervisord as \"simulate:simulate_nbp\"."
echo
yes_no "Do you want to install Strapdown.js?" $DEFAULT_INSTALL_DOC_MARKDOWN
INSTALL_DOC_MARKDOWN=$YES_NO_RESULT

#########################################################################
#########################################################################
# Save defaults in a preferences file for the next time we run.
save_default_variables

#########################################################################
#########################################################################
# Install packages
echo "#####################################################################"
echo "Installing required packages from repository..."
install_packages

#########################################################################
#########################################################################
# Set up OpenRVDAS
echo "#####################################################################"
echo "Fetching and setting up OpenRVDAS code..."
# Expect the following shell variables to be appropriately set:
# INSTALL_ROOT - path where openrvdas/ is
# RVDAS_USER - valid userid
# OPENRVDAS_REPO - path to OpenRVDAS repo
# OPENRVDAS_BRANCH - branch of rep to install
install_openrvdas

#########################################################################
#########################################################################
# Set up virtual env and python-dependent code (Django and uWSGI, etc)
echo "#####################################################################"
echo "Installing virtual environment for Django, uWSGI and other Python-dependent packages."
# Expect the following shell variables to be appropriately set:
# INSTALL_ROOT - path where openrvdas/ is
setup_python_packages

#########################################################################
#########################################################################
# Set up nginx
if [[ "$INSTALL_GUI" == "yes" ]];then
    echo "#####################################################################"
    echo "Setting up NGINX"
    setup_nginx
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

#########################################################################
#########################################################################
# Set up uwsgi
if [[ "$INSTALL_GUI" == "yes" ]];then
    echo
    echo "#####################################################################"
    echo "Setting up UWSGI"
    # Expect the following shell variables to be appropriately set:
    # HOSTNAME - name of host
    # INSTALL_ROOT - path where openrvdas/ is
    setup_uwsgi
fi

#########################################################################
#########################################################################
# Set up Django database
echo
echo "#########################################################################"
echo "Initializing Django database..."
# Expect the following shell variables to be appropriately set:
# RVDAS_USER - valid userid
# RVDAS_DATABASE_PASSWORD - string to use for Django password
setup_django

# Connect uWSGI with our project installation
echo
echo "#####################################################################"
echo "Creating OpenRVDAS-specific uWSGI files"

# Make everything accessible to nginx
sudo chmod 755 ${INSTALL_ROOT}/openrvdas
sudo chown -R ${RVDAS_USER} ${INSTALL_ROOT}/openrvdas
sudo chgrp -R ${RVDAS_GROUP} ${INSTALL_ROOT}/openrvdas

# Create openrvdas log and tmp directories
sudo mkdir -p /var/log/openrvdas /var/tmp/openrvdas
sudo chown $RVDAS_USER /var/log/openrvdas /var/tmp/openrvdas
sudo chgrp $RVDAS_GROUP /var/log/openrvdas /var/tmp/openrvdas

echo
echo "#####################################################################"
echo "Setting up openrvdas service with supervisord"
# Expect the following shell variables to be appropriately set:
# RVDAS_USER - valid username
# INSTALL_ROOT - path where openrvdas/ is found
# OPENRVDAS_AUTOSTART - 'true' if we're to autostart, else 'false'
setup_supervisor

#########################################################################
#########################################################################
# If we've been instructed to set up firewall, do so.
if [ $INSTALL_FIREWALLD == 'yes' ]; then
    setup_firewall
fi

###########################################################################
###########################################################################
# Download and install js script to render .md documents
if [ $INSTALL_DOC_MARKDOWN == 'yes' ]; then
    setup_markdown
fi

echo
echo "#########################################################################"
echo "Restarting services: supervisor"
    # If we're on MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        sudo mkdir -p /usr/local/var/run/
        sudo chown $RVDAS_USER /usr/local/var/run
        sudo chgrp $RVDAS_GROUP /usr/local/var/run

        echo "NOTE: on MacOS, supervisord will not be started automatically."
        echo "To run it, try"
        echo "    sudo /opt/openrvdas/venv/bin/supervisord \\"
        echo "       -c /usr/local/etc/supervisord.conf"
        echo
        read -p "Hit return to continue. " DUMMY_VAR

    # Linux
    elif [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
        sudo mkdir -p /var/run/supervisor/
        sudo chgrp $RVDAS_GROUP /var/run/supervisor

        # CentOS/RHEL
        if [ $OS_TYPE == 'CentOS' ]; then
            sudo systemctl enable supervisord
            sudo systemctl restart supervisord
        else # Ubuntu/Debian
            sudo systemctl enable supervisor
            sudo systemctl restart supervisor
        fi

        if [[ "$INSTALL_GUI" == "yes" ]];then
            # Previous installations used nginx and uwsgi as a service. We need to
            # disable them if they're running.
            echo Disabling legacy services
            sudo systemctl stop nginx 2> /dev/null || echo "nginx not running"
            sudo systemctl disable nginx 2> /dev/null || echo "nginx disabled"
            sudo systemctl stop uwsgi 2> /dev/null || echo "uwsgi not running"
            sudo systemctl disable uwsgi 2> /dev/null || echo "uwsgi disabled"
        fi
    fi

# Deactivate the virtual environment - we'll be calling all relevant
# binaries using their venv paths, so don't need it.
deactivate

echo
echo "#########################################################################"
echo "Installation complete - happy logging!"
echo
