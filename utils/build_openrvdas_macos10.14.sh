#!/bin/bash -e

# OpenRVDAS is available as open source under the MIT License at
#   https:/github.com/oceandatatools/openrvdas
#
# This script installs and configures OpenRVDAS to run on CentOS7.  It
# is designed to be run as root. It should take a (relatively) clean
# CentOS 7 installation and install and configure all the components
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
# browser to http://[hostname]:8000 and see the OpenRVDAS control
# console.
#
# If you selected "no" when asked whether to run OpenRVDAS as a
# service on boot, you will need to manually start the servers:
#
#   supervisorctl start web:*        # start NGINX and UWSGI
#   supervisorctl start openrvdas:*  # start logger_manager and data server
#
# Regardless, running
#
#   supervisorctl status
#
# should show you which services are running.
#
#
# This script is somewhat rudimentary and has not been extensively
# tested. If it fails on some part of the installation, there is no
# guarantee that fixing the specific issue and simply re-running will
# produce the desired result.  Bug reports, and even better, bug
# fixes, will be greatly appreciated.

PREFERENCES_FILE='.build_openrvdas_preferences'

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

    DEFAULT_RVDAS_USER=rvdas

    # Read in the preferences file, if it exists, to overwrite the defaults.
    if [ -e $PREFERENCES_FILE ]; then
        echo Reading pre-saved defaults from "$PREFERENCES_FILE"
        source $PREFERENCES_FILE
        echo branch $DEFAULT_OPENRVDAS_BRANCH
    fi
}

###########################################################################
###########################################################################
# Save defaults in a preferences file for the next time we run.
function save_default_variables {
    cat > $PREFERENCES_FILE <<EOF
# Defaults written by/to be read by build_openrvdas_centos7.sh

DEFAULT_HOSTNAME=$HOSTNAME
DEFAULT_INSTALL_ROOT=$INSTALL_ROOT

#DEFAULT_HTTP_PROXY=proxy.lmg.usap.gov:3128 #$HTTP_PROXY
DEFAULT_HTTP_PROXY=$HTTP_PROXY

DEFAULT_OPENRVDAS_REPO=$OPENRVDAS_REPO
DEFAULT_OPENRVDAS_BRANCH=$OPENRVDAS_BRANCH

DEFAULT_RVDAS_USER=$RVDAS_USER
EOF
}

###########################################################################
###########################################################################
# Set hostname
function set_hostname {
    HOSTNAME=$1
    #hostnamectl set-hostname $HOSTNAME
    #echo $HOSTNAME > /etc/hostname
    #ETC_HOSTS_LINE="127.0.1.1	$HOSTNAME"
    #if grep -q "$ETC_HOSTS_LINE" /etc/hosts ; then
    #    echo Hostname already in /etc/hosts
    #else
    #    echo "$ETC_HOSTS_LINE" >> /etc/hosts
    #fi
}

###########################################################################
###########################################################################
# Create user
#function create_user {
#    RVDAS_USER=$1
#
#    echo Checking if user $RVDAS_USER exists yet
#    if id -u $RVDAS_USER > /dev/null; then
#        echo User exists, skipping
#    else
#        echo Creating $RVDAS_USER
#        adduser --gecos "" $RVDAS_USER
#        #passwd $RVDAS_USER
#        usermod -a -G tty $RVDAS_USER
#    fi
#}

###########################################################################
###########################################################################
# Install and configure required packages
function install_packages {
    # Install homebrew:
    echo Checking for homebrew
    [ -e /usr/local/bin/brew ] || echo Installing homebrew
    [ -e /usr/local/bin/brew ] || ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

    # Install git:
    echo Looking for/installing git
    [ -e /usr/local/bin/git ] || brew install git

    # Install system packages we need
    echo Installing python and supporting packages
    [ -e /usr/local/bin/python ] || brew install python
    [ -e /usr/local/bin/socat ]  || brew install socat
    [ -e /usr/local/bin/ssh ]    || brew install openssh
    [ -e /usr/local/bin/nginx ]  || brew install nginx
    [ -e /usr/local/bin/supervisorctl ] || brew install supervisor

    brew upgrade socat openssh nginx supervisor || echo Upgraded packages
    brew link --overwrite python || echo Linking Python
}

###########################################################################
###########################################################################
# Install and configure database
function install_mysql {
    # Expect the following shell variables to be appropriately set:
    # RVDAS_USER - valid userid
    # RVDAS_DATABASE_PASSWORD - current rvdas user MySQL database password
    # NEW_ROOT_DATABASE_PASSWORD - new root password to use for MySQL
    # CURRENT_ROOT_DATABASE_PASSWORD - current root password for MySQL

    echo "#####################################################################"
    echo Installing and enabling MySQL...
    [ -e /usr/local/bin/mysql ]  || brew install mysql
    brew upgrade mysql || echo Upgraded database package
    brew tap homebrew/services
    brew services restart mysql

    echo "#####################################################################"
    echo Setting up database tables and permissions
    # Verify current root password for mysql
    while true; do
        # Check whether they're right about the current password; need
        # a special case if the password is empty.
        PASS=TRUE
        [ ! -z $CURRENT_ROOT_DATABASE_PASSWORD ] || (mysql -u root  < /dev/null) || PASS=FALSE
        [ -z $CURRENT_ROOT_DATABASE_PASSWORD ] || (mysql -u root -p$CURRENT_ROOT_DATABASE_PASSWORD < /dev/null) || PASS=FALSE
        case $PASS in
            TRUE ) break;;
            * ) echo "Database root password failed";read -p "Current database password for root? (if one exists - hit return if not) " CURRENT_ROOT_DATABASE_PASSWORD;;
        esac
    done

    # Set the new root password
    cat > /tmp/set_pwd <<EOF
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$NEW_ROOT_DATABASE_PASSWORD';
FLUSH PRIVILEGES;
EOF

    # If there's a current root password
    [ -z $CURRENT_ROOT_DATABASE_PASSWORD ] || mysql -u root -p$CURRENT_ROOT_DATABASE_PASSWORD < /tmp/set_pwd

    # If there's no current root password
    [ ! -z $CURRENT_ROOT_DATABASE_PASSWORD ] || mysql -u root < /tmp/set_pwd
    rm -f /tmp/set_pwd

    # Now do the rest of the 'mysql_safe_installation' stuff
    mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD <<EOF
DELETE FROM mysql.user WHERE User='root' AND Host NOT IN ('localhost', '127.0.0.1', '::1');
DELETE FROM mysql.user WHERE User='';
DELETE FROM mysql.db WHERE Db='test' OR Db='test_%';
FLUSH PRIVILEGES;
EOF

    echo "#####################################################################"
    echo Setting up database users
    mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD <<EOF
drop user if exists 'test'@'localhost';
create user 'test'@'localhost' identified by 'test';

drop user if exists '$RVDAS_USER'@'localhost';
create user '$RVDAS_USER'@'localhost' identified by '$RVDAS_DATABASE_PASSWORD';

create database if not exists data character set utf8;
GRANT ALL PRIVILEGES ON data.* TO '$RVDAS_USER'@'localhost';

create database if not exists test character set utf8;
GRANT ALL PRIVILEGES ON test.* TO '$RVDAS_USER'@'localhost';
GRANT ALL PRIVILEGES ON test.* TO 'test'@'localhost';

flush privileges;
\q
EOF
    echo Done setting up database
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
      echo Making install directory "$INSTALL_ROOT"
      sudo mkdir -p $INSTALL_ROOT
      sudo chown ${RVDAS_USER} $INSTALL_ROOT
    fi

    cd $INSTALL_ROOT
    if [ ! -e openrvdas ]; then
      echo Making openrvdas directory.
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

    # A stupid MacOS-only hack we need to make because MacOS doesn't
    # do well with supervisord's attempt to be available from all
    # hosts via http.  Make it available only to localhost.
    sed -i.bak 's/port=\*/port=localhost/' server/logger_manager.py

    # Copy widget settings into place and customize for this machine
    cp display/js/widgets/settings.js.dist \
       display/js/widgets/settings.js
    sed -i -e "s/localhost/${HOSTNAME}/g" display/js/widgets/settings.js

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
    # INSTALL_MYSQL - set if MySQL is to be installed, unset otherwise

    # Set up virtual environment
    VENV_PATH=$INSTALL_ROOT/openrvdas/venv
    python3 -m venv $VENV_PATH
    source $VENV_PATH/bin/activate  # activate virtual environment

    # Inside the venv, python *is* the right version, right?
    python3 -m pip install --upgrade pip
    pip3 install \
      Django==3 \
      pyserial \
      uwsgi \
      websockets \
      PyYAML \
      parse \
      psutil \
      supervisor

    # If we're installing database, then also install relevant
    # Python clients.
    if [ -n "$INSTALL_MYSQL" ]; then
      pip3 install \
        mysqlclient \
        mysql-connector
    fi
}

###########################################################################
###########################################################################
# Set up NGINX
function setup_nginx {
    # Disable because we're going to run it via supervisor
    #systemctl stop nginx
    #systemctl disable nginx # NGINX seems to be enabled by default?

    [ -e /usr/local/etc/nginx/sites-available ] || mkdir /usr/local/etc/nginx/sites-available
    [ -e /usr/local/etc/nginx/sites-enabled ] || mkdir /usr/local/etc/nginx/sites-enabled

    # We need to add a couple of lines to not quite the end of nginx.conf,
    # so do a bit of hackery: chop off the closing "}" with head, append
    # the lines we need and a new closing "}" into a temp file, then copy back.
    if grep -q "/usr/local/etc/nginx/sites-enabled/" /usr/local/etc/nginx/nginx.conf; then
        echo NGINX sites-available already registered. Skipping...
    else
        sed -i.bak 's/include servers\/\*;/include \/usr\/local\/etc\/nginx\/sites-enabled\/\*.conf\;\
    server_names_hash_bucket_size 64\;/' /usr/local/etc/nginx/nginx.conf
        echo Done setting up NGINX
    fi
}

###########################################################################
###########################################################################
# Set up Django
function setup_django {
    # Expect the following shell variables to be appropriately set:
    # RVDAS_USER - valid userid
    # RVDAS_DATABASE_PASSWORD - string to use for Django password

    cd ${INSTALL_ROOT}/openrvdas
    cp django_gui/settings.py.dist django_gui/settings.py
    sed -i -e "s/'USER': 'rvdas'/'USER': '${RVDAS_USER}'/g" django_gui/settings.py
    sed -i -e "s/'PASSWORD': 'rvdas'/'PASSWORD': '${RVDAS_DATABASE_PASSWORD}'/g" django_gui/settings.py

    # NOTE: we're still inside virtualenv, so we're getting the python
    # that was installed under it.
    python manage.py makemigrations django_gui
    python manage.py migrate
    rm -rf static
    python manage.py collectstatic --no-input --clear --link -v 0
    chmod -R og+rX static

    # A temporary hack to allow the display/ pages to be accessed by Django
    # in their old location of static/widgets/
    cd static;ln -s html widgets;cd ..

    # Bass-ackwards way of creating superuser $RVDAS_USER, as the
    # createsuperuser command won't work from a script
    python manage.py shell <<EOF
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

    cp /usr/local/etc/nginx/uwsgi_params $INSTALL_ROOT/openrvdas/django_gui

    cat > $INSTALL_ROOT/openrvdas/django_gui/openrvdas_nginx.conf<<EOF
# openrvdas_nginx.conf

# the upstream component nginx needs to connect to
upstream django {
    server unix://${INSTALL_ROOT}/openrvdas/django_gui/openrvdas.sock; # for a file socket
}

# configuration of the server
server {
    # the port your site will be served on
    listen      8000;
    # the domain name it will serve for
    server_name ${HOSTNAME}; # substitute machine's IP address or FQDN
    charset     utf-8;

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
    }
    location /css {
        alias /${INSTALL_ROOT}/openrvdas/display/css; # display pages
    }

    location /static {
        alias ${INSTALL_ROOT}/openrvdas/static; # project static files
        autoindex on;
    }

    location /docs {
        alias ${INSTALL_ROOT}/openrvdas/docs; # project doc files
        autoindex on;
    }

    # Finally, send all non-media requests to the Django server.
    location / {
        uwsgi_pass  django;
        include     ${INSTALL_ROOT}/openrvdas/django_gui/uwsgi_params;
    }
}
EOF

    # Make symlink to nginx dir
    ln -sf ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_nginx.conf /usr/local/etc/nginx/sites-enabled

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
    [ -e /usr/local/etc/uwsgi/vassals ] || mkdir -p /usr/local/etc/uwsgi/vassals
    ln -sf ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_uwsgi.ini \
          /usr/local/etc/uwsgi/vassals/
}

###########################################################################
###########################################################################
# Set up supervisord files
function setup_supervisor {
    # Expect the following shell variables to be appropriately set:
    # RVDAS_USER - valid username
    # INSTALL_ROOT - path where openrvdas/ is found
    # OPENRVDAS_AUTOSTART - 'true' if we're to autostart, else 'false'

    VENV_BIN=${INSTALL_ROOT}/openrvdas/venv/bin

    cat > /tmp/openrvdas.ini <<EOF
; First, override the default socket permissions to allow user
; $RVDAS_USER to run supervisorctl
[unix_http_server]
  file=/usr/local/var/run/supervisor.sock   ; (the path to the socket file)
chmod=0770                      ; socket file mode (default 0700)
;chown=nobody:${RVDAS_USER} ; CAN'T GET THIS TO WORK WITH MACOS

[inet_http_server]
port=127.0.0.1:9001
;username=${RVDAS_USER}  ; Disabled for MacOS installation
;password=${RVDAS_USER}  ; "   "

; The scripts we're going to run
[program:nginx]
command=/usr/local/bin/nginx -g 'daemon off;'
directory=${INSTALL_ROOT}/openrvdas
autostart=$OPENRVDAS_AUTOSTART
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/nginx.stderr
stdout_logfile=/var/log/openrvdas/nginx.stdout
;user=$RVDAS_USER

[program:uwsgi]
command=${VENV_BIN}/uwsgi ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_uwsgi.ini --thunder-lock --enable-threads
stopsignal=INT
directory=${INSTALL_ROOT}/openrvdas
autostart=$OPENRVDAS_AUTOSTART
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/uwsgi.stderr
stdout_logfile=/var/log/openrvdas/uwsgi.stdout
;user=$RVDAS_USER

[program:cached_data_server]
command=${VENV_BIN}/python server/cached_data_server.py --port 8766 --disk_cache /var/tmp/openrvdas/disk_cache --max_records 8640 -v
directory=${INSTALL_ROOT}/openrvdas
autostart=$OPENRVDAS_AUTOSTART
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/cached_data_server.stderr
stdout_logfile=/var/log/openrvdas/cached_data_server.stdout
;user=$RVDAS_USER

[program:logger_manager]
command=${VENV_BIN}/python server/logger_manager.py --database django --no-console --data_server_websocket :8766 -v -V
environment=PATH="${VENV_BIN}:/usr/bin:/usr/local/bin"
directory=${INSTALL_ROOT}/openrvdas
autostart=$OPENRVDAS_AUTOSTART
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/logger_manager.stderr
stdout_logfile=/var/log/openrvdas/logger_manager.stdout
;user=$RVDAS_USER

[program:simulate_nbp]
command=${VENV_BIN}/python logger/utils/simulate_data.py --config test/NBP1406/simulate_NBP1406.yaml
directory=${INSTALL_ROOT}/openrvdas
autostart=false
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/simulate_nbp.stderr
stdout_logfile=/var/log/openrvdas/simulate_nbp.stdout
;user=$RVDAS_USER

[group:web]
programs=nginx,uwsgi

[group:openrvdas]
programs=logger_manager,cached_data_server

[group:simulate]
programs=simulate_nbp
EOF

    echo Please enter sudo password if prompted...
    sudo mkdir -p /usr/local/etc/supervisor.d/
    sudo cp /tmp/openrvdas.ini /usr/local/etc/supervisor.d/openrvdas.ini
}

###########################################################################
###########################################################################
###########################################################################
###########################################################################
# Start of actual script
###########################################################################
###########################################################################

# Read from the preferences file in $PREFERENCES_FILE, if it exists
set_default_variables

#if [ "$(whoami)" != "root" ]; then
#  echo "ERROR: installation script must be run as root."
#  return -1 2> /dev/null || exit -1  # terminate correctly if sourced/bashed
#fi

# Set creation mask so that everything we install is, by default,
# world readable/executable.
umask 022

echo "#####################################################################"
echo OpenRVDAS configuration script

#echo "#####################################################################"
#read -p "Name to assign to host ($DEFAULT_HOSTNAME)? " HOSTNAME
#HOSTNAME=${HOSTNAME:-$DEFAULT_HOSTNAME}
#echo "Hostname will be '$HOSTNAME'"
## Set hostname
#set_hostname $HOSTNAME

read -p "Install root? ($DEFAULT_INSTALL_ROOT) " INSTALL_ROOT
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

echo Will install from github.com
echo "Repository: '$OPENRVDAS_REPO'"
echo "Branch: '$OPENRVDAS_BRANCH'"
echo

# NOTE: On MacOS, creating a new user is a mess. We'll just prompt to
# use an existing user.

echo "#####################################################################"
read -p "Existing user to set system up for? ($DEFAULT_RVDAS_USER) " RVDAS_USER
RVDAS_USER=${RVDAS_USER:-$DEFAULT_RVDAS_USER}
#create_user $RVDAS_USER

echo
read -p "Django/database password to use for user $RVDAS_USER? ($RVDAS_USER) " RVDAS_DATABASE_PASSWORD
RVDAS_DATABASE_PASSWORD=${RVDAS_DATABASE_PASSWORD:-$RVDAS_USER}

#########################################################################
#########################################################################
# Do they want to install/configure MySQL for use by DatabaseWriter, etc?
echo "#####################################################################"
echo MySQL can be installed and configured so that DatabaseWriter and
echo DatabaseReader have something to write to and read from.
while true; do
    read -p "Do you wish to install and configure MySQL? (no) " yn
    case $yn in
        [Yy]* )
            INSTALL_MYSQL=True
            break;;
        [Nn]* )
            unset INSTALL_MYSQL
            break;;
        "" )
            unset INSTALL_MYSQL
            break;;
        * ) echo "Please answer yes or no.";;
    esac
done
echo

if [ -n "$INSTALL_MYSQL" ]; then
    echo Will install/configure MySQL
    # Get current and new passwords for database
    echo Root database password will be empty on initial installation. If this
    echo is the initial installation, hit "return" when prompted for root
    echo database password, otherwise enter the password you used during the
    echo initial installation.
    echo
    echo Current database password for root \(hit return if this is the
    read -p "initial installation)? " CURRENT_ROOT_DATABASE_PASSWORD
    read -p "New database password for root? ($CURRENT_ROOT_DATABASE_PASSWORD) " NEW_ROOT_DATABASE_PASSWORD
    NEW_ROOT_DATABASE_PASSWORD=${NEW_ROOT_DATABASE_PASSWORD:-$CURRENT_ROOT_DATABASE_PASSWORD}
else
    echo Skipping MySQL installation/configuration
fi

#########################################################################
#########################################################################
# Start OpenRVDAS as a service?
echo "#####################################################################"
echo The OpenRVDAS server can be configured to start on boot. If you wish this
echo to happen, it will be run/monitored by the supervisord service using the
echo configuration file in /usr/local/etc/supervisord.d/openrvdas.ini.
echo
echo If you do not wish it to start automatically, it may still be run manually
echo from the command line or started via supervisor by running supervisorctl
echo and starting processes logger_manager and cached_data_server.
echo
OPENRVDAS_AUTOSTART=false
while true; do
    read -p "Do you wish to start the OpenRVDAS server on boot? (yes) " yn
    case $yn in
        [Yy]* )
            OPENRVDAS_AUTOSTART=true
            echo Will enable openrvdas server run on boot.
            break;;
        "" )
            OPENRVDAS_AUTOSTART=true
            echo Will enable openrvdas server run on boot.
            break;;
        [Nn]* )
            break;;
        * ) echo "Please answer yes or no.";;
    esac
done

#########################################################################
#########################################################################
# Save defaults in a preferences file for the next time we run.
save_default_variables

#########################################################################
#########################################################################
# Install packages
echo "#####################################################################"
echo Installing required packages from repository...
install_packages

#########################################################################
#########################################################################
# If we're installing MySQL/MariaDB
echo "#####################################################################"
if [ -n "$INSTALL_MYSQL" ]; then
    echo Installing/configuring database
    # Expect the following shell variables to be appropriately set:
    # RVDAS_USER - valid userid
    # RVDAS_DATABASE_PASSWORD - current rvdas user MySQL database password
    # NEW_ROOT_DATABASE_PASSWORD - new root password to use for MySQL
    # CURRENT_ROOT_DATABASE_PASSWORD - current root password for MySQL
    install_mysql
else
    echo Skipping database setup
fi

#########################################################################
#########################################################################
# Set up OpenRVDAS
echo "#####################################################################"
echo Fetching and setting up OpenRVDAS code...
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
echo Installing virtual environment for Django, uWSGI and other Python-dependent packages.
# Expect the following shell variables to be appropriately set:
# INSTALL_ROOT - path where openrvdas/ is
# INSTALL_MYSQL - set if MySQL is to be installed, unset otherwise
setup_python_packages

#########################################################################
#########################################################################
# Set up nginx
echo "#####################################################################"
echo Setting up NGINX
setup_nginx

#########################################################################
#########################################################################
# Set up uwsgi
echo "#####################################################################"
echo Setting up UWSGI
# Expect the following shell variables to be appropriately set:
# HOSTNAME - name of host
# INSTALL_ROOT - path where openrvdas/ is
setup_uwsgi

#cat > /etc/profile.d/openrvdas.sh <<EOF
#export PYTHONPATH=$PYTHONPATH:${INSTALL_ROOT}/openrvdas
#export PATH=$PATH:${INSTALL_ROOT}/openrvdas/logger/listener
#EOF

#########################################################################
#########################################################################
# Set up Django database
echo "#########################################################################"
echo Initializing Django database...
# Expect the following shell variables to be appropriately set:
# RVDAS_USER - valid userid
# RVDAS_DATABASE_PASSWORD - string to use for Django password
setup_django

# Connect uWSGI with our project installation
echo "#####################################################################"
echo Creating OpenRVDAS-specific uWSGI files

# Make everything accessible to nginx
chmod 755 ${INSTALL_ROOT}/openrvdas
chown -R ${RVDAS_USER} ${INSTALL_ROOT}/openrvdas
#chgrp -R ${RVDAS_USER} ${INSTALL_ROOT}/openrvdas

# Create openrvdas log and tmp directories
echo Creating openrvdas working directories in /var/tmp
echo Please enter sudo password if prompted...
sudo mkdir -p /var/log/openrvdas /var/tmp/openrvdas
sudo chown $RVDAS_USER /var/log/openrvdas /var/tmp/openrvdas

echo "#####################################################################"
echo Setting up openrvdas service with supervisord
# Expect the following shell variables to be appropriately set:
# RVDAS_USER - valid username
# INSTALL_ROOT - path where openrvdas/ is found
# OPENRVDAS_AUTOSTART - 'true' if we're to autostart, else 'false'
setup_supervisor

#########################################################################
#########################################################################
# If we've been instructed to set up firewall, do so.
#if [ -n "$INSTALL_FIREWALLD" ]; then
#    setup_firewall
#fi

echo "#########################################################################"
echo Restarting services: supervisor
sudo mkdir -p /usr/local/var/run/
sudo chown $RVDAS_USER /usr/local/var/run
brew tap homebrew/services
brew services restart supervisor

## Previous installations used nginx and uwsgi as a service. We need to
## disable them if they're running.
#echo Disabling legacy services
#systemctl stop nginx 2> /dev/null || echo nginx not running
#systemctl disable nginx 2> /dev/null || echo nginx disabled
#systemctl stop uwsgi 2> /dev/null || echo uwsgi not running
#systemctl disable uwsgi 2> /dev/null || echo uwsgi disabled

# Deactivate the virtual environment - we'll be calling all relevant
# binaries using their venv paths, so don't need it.
deactivate

echo "#########################################################################"
echo Installation complete - happy logging!
echo
