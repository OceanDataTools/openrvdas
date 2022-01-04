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

PREFERENCES_FILE='.install_openrvdas_preferences'

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
        if [[ `uname -p` == 'arm' ]];then
            echo
            echo "WARNING: As of 11/20/2020, Homebrew did not yet support ARM architecture on"
            echo "MacOS. If installation fails, please try installing using the built-in Rosetta"
            echo "interpreter: Make a copy of /Applications/Terminal.app (e.g. RTerminal.app)."
            echo "Select it in the Finder and open its information pane (Clover-I). Select "
            echo "'Open using Rosetta', and use this copy of Terminal when installing OpenRVDAS."
            echo
            read -p "Hit return to continue. " DUMMY_VAR
            echo
        fi
    elif [[ `uname -s` == 'Linux' ]];then
        if [[ ! -z `grep "NAME=\"Ubuntu\"" /etc/os-release` ]];then
            OS_TYPE=Ubuntu
            if [[ ! -z `grep "VERSION_ID=\"18" /etc/os-release` ]];then
                OS_VERSION=18
            elif [[ ! -z `grep "VERSION_ID=\"20" /etc/os-release` ]];then
                OS_VERSION=20
            else
                echo "Sorry - unknown OS Version! - exiting."
                exit_gracefully
            fi
        elif [[ ! -z `grep "NAME=\"CentOS Linux\"" /etc/os-release` ]] || [[ ! -z `grep "NAME=\"Red Hat Enterprise Linux Server\"" /etc/os-release` ]]  || [[ ! -z `grep "NAME=\"Red Hat Enterprise Linux Workstation\"" /etc/os-release` ]];then
            OS_TYPE=CentOS
            if [[ ! -z `grep "VERSION_ID=\"7" /etc/os-release` ]];then
                OS_VERSION=7
            elif [[ ! -z `grep "VERSION_ID=\"8" /etc/os-release` ]];then
                OS_VERSION=8
            else
                echo "Sorry - unknown OS Version! - exiting."
                exit_gracefully
            fi
        else
            echo "Unknown Linux variant!"
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

    DEFAULT_INSTALL_MYSQL=no
    DEFAULT_INSTALL_FIREWALLD=no
    DEFAULT_OPENRVDAS_AUTOSTART=yes

    DEFAULT_SUPERVISORD_WEBINTERFACE=no
    DEFAULT_SUPERVISORD_WEBINTERFACE_AUTH=no
    DEFAULT_SUPERVISORD_WEBINTERFACE_PORT=9001

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

DEFAULT_NONSSL_SERVER_PORT=$NONSSL_SERVER_PORT
DEFAULT_SSL_SERVER_PORT=$SSL_SERVER_PORT

DEFAULT_USE_SSL=$USE_SSL
DEFAULT_HAVE_SSL_CERTIFICATE=$HAVE_SSL_CERTIFICATE
DEFAULT_SSL_CRT_LOCATION=$SSL_CRT_LOCATION
DEFAULT_SSL_KEY_LOCATION=$SSL_KEY_LOCATION

DEFAULT_RVDAS_USER=$RVDAS_USER

DEFAULT_INSTALL_MYSQL=$INSTALL_MYSQL
DEFAULT_INSTALL_FIREWALLD=$INSTALL_FIREWALLD
DEFAULT_OPENRVDAS_AUTOSTART=$OPENRVDAS_AUTOSTART

DEFAULT_SUPERVISORD_WEBINTERFACE=$SUPERVISORD_WEBINTERFACE
DEFAULT_SUPERVISORD_WEBINTERFACE_AUTH=$SUPERVISORD_WEBINTERFACE_AUTH
DEFAULT_SUPERVISORD_WEBINTERFACE_PORT=$SUPERVISORD_WEBINTERFACE_PORT

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
        hostnamectl set-hostname $HOSTNAME
        echo "HOSTNAME=$HOSTNAME" > /etc/sysconfig/network

    # Ubuntu/Debian
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        hostnamectl set-hostname $HOSTNAME
        echo $HOSTNAME > /etc/hostname
    fi

    ETC_HOSTS_LINE="127.0.1.1	$HOSTNAME"
    if grep -q "$ETC_HOSTS_LINE" /etc/hosts ; then
        echo Hostname already in /etc/hosts
    else
        echo "$ETC_HOSTS_LINE" >> /etc/hosts
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
        return
    fi

    # MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
      echo No such pre-existing user: $RVDAS.
      echo On MacOS, must install for pre-existing user. Exiting.
      exit_gracefully

    # CentOS/RHEL
    elif [ $OS_TYPE == 'CentOS' ]; then
        echo Creating $RVDAS_USER
        adduser $RVDAS_USER
        passwd $RVDAS_USER
        usermod -a -G tty $RVDAS_USER
        usermod -a -G wheel $RVDAS_USER

    # Ubuntu/Debian
    elif [ $OS_TYPE == 'Ubuntu' ]; then
          echo Creating $RVDAS_USER
          adduser --gecos "" $RVDAS_USER
          #passwd $RVDAS_USER
          usermod -a -G tty $RVDAS_USER
          usermod -a -G sudo $RVDAS_USER
    fi
}

###########################################################################
###########################################################################
# Install and configure required packages
function install_packages {

    # MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        # Install homebrew:
        echo Checking for homebrew
        [ -e /usr/local/bin/brew ] || echo Installing homebrew
        [ -e /usr/local/bin/brew ] || ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

        # Install git:
        echo Looking for/installing git
        [ -e /usr/local/bin/git ] || brew install git

        # Install system packages we need
        echo Installing python and supporting packages
        [ -e /usr/local/bin/python3 ] || brew install python
        [ -e /usr/local/bin/ssh ]    || brew install openssh
        [ -e /usr/local/bin/nginx ]  || brew install nginx
        [ -e /usr/local/bin/supervisorctl ] || brew install supervisor

        brew upgrade openssh nginx supervisor || echo Upgraded packages
        brew link --overwrite python || echo Linking Python

    # CentOS/RHEL
    elif [ $OS_TYPE == 'CentOS' ]; then
        if [ $OS_VERSION == '7' ]; then
            yum install -y deltarpm
        fi
        yum install -y epel-release
        yum -y update

        echo Installing required packages
        yum install -y wget git nginx gcc supervisor \
            zlib-devel openssl-devel readline-devel libffi-devel

            #sqlite-devel \
            #python3 python3-devel python3-pip

        # Django 3+ requires a more recent version of sqlite3 than is
        # included in CentOS 7. So instead of yum installing python3 and
        # sqlite3, we build them from scratch. Painfully slow, but hey -
        # isn't that par for CentOS builds?
        export LD_LIBRARY_PATH=/usr/local/lib
        export LD_RUN_PATH=/usr/local/lib

        # Fetch and build SQLite3
        SQLITE_VERSION=3320300
        if [ `/usr/local/bin/sqlite3 --version |  cut -f1 -d' '` == '3.32.3' ]; then
            echo Already have appropriate version of sqlite3
        else
            cd /var/tmp
            SQLITE_BASE=sqlite-autoconf-${SQLITE_VERSION}
            SQLITE_TGZ=${SQLITE_BASE}.tar.gz
            [ -e $SQLITE_TGZ ] || wget https://www.sqlite.org/2020/${SQLITE_TGZ}
            tar xzf ${SQLITE_TGZ}
            cd ${SQLITE_BASE}
            sh ./configure
            make && make install
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
                make altinstall

                ln -s -f /usr/local/bin/python3.8 /usr/local/bin/python3
                ln -s -f /usr/local/bin/pip3.8 /usr/local/bin/pip3
            fi
        elif [ $OS_VERSION == '8' ]; then
            yum install -y python3 python3-devel
        else
            echo "Install error: unknown OS_VERSION should have been caught earlier?!?"
            exit_gracefully
        fi

    # Ubuntu/Debian
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        apt-get update
        apt install -y git nginx libreadline-dev \
            python3-dev python3-pip python3-venv libsqlite3-dev \
            openssh-server supervisor libssl-dev
    fi
}

###########################################################################
###########################################################################
function install_mysql_macos {
    echo "#####################################################################"
    echo "Installing and enabling MySQL..."
    [ -e /usr/local/bin/mysql ]  || brew install mysql
    brew upgrade mysql || echo Upgraded database package
    brew tap homebrew/services
    brew services restart mysql

    echo "#####################################################################"
    echo "Setting up database tables and permissions"
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
    echo "Setting up database users"
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
function install_mysql_centos {
    echo "#####################################################################"
    echo "Installing and enabling Mariadb (MySQL replacement in CentOS 7)..."

    yum install -y  mariadb-server mariadb-devel
    if [ $OS_VERSION == '7' ]; then
        yum install -y mariadb-libs
    fi
    systemctl restart mariadb              # to manually start db server
    systemctl enable mariadb               # to make it start on boot

    echo "#####################################################################"
    echo "Setting up database tables and permissions"
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
UPDATE mysql.user SET Password=PASSWORD('$NEW_ROOT_DATABASE_PASSWORD') WHERE User='root';
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

    # Try creating databases. Command will fail if they exist, so we need
    # to do one at a time and trap any possible errors.
    mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD <<EOF > /dev/null || echo "table \"data\" appears to already exist - no problem"
create database data character set utf8;
EOF

    mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD <<EOF
GRANT ALL PRIVILEGES ON data.* TO $RVDAS_USER@localhost IDENTIFIED BY '$RVDAS_DATABASE_PASSWORD' WITH GRANT OPTION;

GRANT ALL PRIVILEGES ON test.* TO $RVDAS_USER@localhost IDENTIFIED BY '$RVDAS_DATABASE_PASSWORD' WITH GRANT OPTION;
GRANT ALL PRIVILEGES ON test.* TO test@localhost IDENTIFIED BY 'test' WITH GRANT OPTION;
FLUSH PRIVILEGES;
EOF
    echo "Done setting up MariaDB"
}

###########################################################################
###########################################################################
function install_mysql_ubuntu {
    echo "#####################################################################"
    echo "Installing and enabling MySQL..."

    apt install -y mysql-server mysql-common mysql-client libmysqlclient-dev
    systemctl restart mysql    # to manually start db server
    systemctl enable mysql     # to make it start on boot

    echo "#####################################################################"
    echo "Setting up database tables and permissions"
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

    # Start mysql to start up as a service
    update-rc.d mysql defaults

    echo "#####################################################################"
    echo "Setting up database users"
    mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD <<EOF
drop user if exists 'test'@'localhost';
create user 'test'@'localhost' identified by 'test';

drop user if exists 'rvdas'@'localhost';
create user '$RVDAS_USER'@'localhost' identified by '$RVDAS_DATABASE_PASSWORD';

create database if not exists data character set utf8;
GRANT ALL PRIVILEGES ON data.* TO '$RVDAS_USER'@'localhost';

create database if not exists test character set utf8;
GRANT ALL PRIVILEGES ON test.* TO '$RVDAS_USER'@'localhost';
GRANT ALL PRIVILEGES ON test.* TO 'test'@'localhost';

flush privileges;
\q
EOF
    echo "Done setting up MySQL"

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

    # MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        install_mysql_macos

    # CentOS/RHEL
    elif [ $OS_TYPE == 'CentOS' ]; then
        install_mysql_centos

    # Ubuntu/Debian
    elif [ $OS_TYPE == 'Ubuntu' ]; then
         install_mysql_ubuntu
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
    # INSTALL_MYSQL - set if MySQL is to be installed, unset otherwise

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

    python3 -m venv $VENV_PATH
    source $VENV_PATH/bin/activate  # activate virtual environment

    pip install \
      --trusted-host pypi.org --trusted-host files.pythonhosted.org \
      --upgrade pip
    pip install \
      --trusted-host pypi.org --trusted-host files.pythonhosted.org \
      wheel  # To help with the rest of the installations

    pip install -r utils/requirements.txt

    # If we're installing database, then also install relevant
    # Python clients.
    if [ $INSTALL_MYSQL == 'yes' ]; then
      pip install -r utils/requirements_mysql.txt
    fi
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

    # Put the nginx conf file in place and link it up
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
    cp django_gui/settings.py.dist django_gui/settings.py
    sed -i -e "s/WEBSOCKET_PROTOCOL = 'ws'/WEBSOCKET_PROTOCOL = '${WEBSOCKET_PROTOCOL}'/g" django_gui/settings.py
    sed -i -e "s/WEBSOCKET_PORT = 80/WEBSOCKET_PORT = ${SERVER_PORT}/g" django_gui/settings.py
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
    ln -sf ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_uwsgi.ini \
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

    VENV_BIN=${INSTALL_ROOT}/openrvdas/venv/bin
    if [ $OPENRVDAS_AUTOSTART = 'yes' ]; then
        AUTOSTART=true
    else
        AUTOSTART=false
    fi

    # MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        ETC_HOME=/usr/local/etc
        HTTP_HOST=127.0.0.1
        NGINX_BIN=/usr/local/bin/nginx
        SUPERVISOR_DIR=/usr/local/etc/supervisor.d/
        SUPERVISOR_FILE=$SUPERVISOR_DIR/openrvdas.ini
        SUPERVISOR_SOCK=/usr/local/var/run/supervisor.sock
        COMMENT_SOCK_OWNER=';'

    # CentOS/RHEL
    elif [ $OS_TYPE == 'CentOS' ]; then
        ETC_HOME=/etc
        HTTP_HOST='*'
        NGINX_BIN=/usr/sbin/nginx
        SUPERVISOR_DIR=/etc/supervisord.d
        SUPERVISOR_FILE=$SUPERVISOR_DIR/openrvdas.ini
        SUPERVISOR_SOCK=/var/run/supervisor/supervisor.sock
        COMMENT_SOCK_OWNER=''

    # Ubuntu/Debian
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        ETC_HOME=/etc
        HTTP_HOST='*'
        NGINX_BIN=/usr/sbin/nginx
        SUPERVISOR_DIR=/etc/supervisor/conf.d
        SUPERVISOR_FILE=$SUPERVISOR_DIR/openrvdas.conf
        SUPERVISOR_SOCK=/var/run/supervisor.sock
        COMMENT_SOCK_OWNER=''

    fi

    # Write out supervisor file, filling in variables
    cat > /tmp/openrvdas.ini <<EOF
; First, override the default socket permissions to allow user
; $RVDAS_USER to run supervisorctl
[unix_http_server]
file=$SUPERVISOR_SOCK   ; (the path to the socket file)
chmod=0770              ; socket file mode (default 0700)
${COMMENT_SOCK_OWNER}chown=nobody:${RVDAS_USER}
EOF

    if [ $SUPERVISORD_WEBINTERFACE == 'yes' ]; then
        cat >> /tmp/openrvdas.ini <<EOF

[inet_http_server]
port=${SUPERVISORD_WEBINTERFACE_PORT}
EOF
        if [ $SUPERVISORD_WEBINTERFACE_AUTH == 'yes' ]; then
            SUPERVISORD_WEBINTERFACE_HASH=`echo -n ${SUPERVISORD_WEBINTERFACE_PASS} | sha1sum | awk '{printf("{SHA}%s",$1)}'`
            cat >> /tmp/openrvdas.ini <<EOF
username=${SUPERVISORD_WEBINTERFACE_USER}
password=${SUPERVISORD_WEBINTERFACE_HASH} ; echo -n "<password>" | sha1sum | awk '{printf("{SHA}%s",\$1)}'
EOF
        fi
    fi

    cat >> /tmp/openrvdas.ini <<EOF

; The scripts we're going to run
[program:nginx]
command=${NGINX_BIN} -g 'daemon off;' -c ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_nginx.conf
directory=${INSTALL_ROOT}/openrvdas
autostart=$AUTOSTART
autorestart=true
startretries=3
killasgroup=true
stderr_logfile=/var/log/openrvdas/nginx.stderr
stderr_logfile_maxbytes=10000000 ; 10M
stderr_logfile_maxbackups=100
;user=$RVDAS_USER

[program:uwsgi]
command=${VENV_BIN}/uwsgi ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_uwsgi.ini --thunder-lock --enable-threads
stopsignal=INT
directory=${INSTALL_ROOT}/openrvdas
autostart=$AUTOSTART
autorestart=true
startretries=3
killasgroup=true
stderr_logfile=/var/log/openrvdas/uwsgi.stderr
stderr_logfile_maxbytes=10000000 ; 10M
stderr_logfile_maxbackups=100
user=$RVDAS_USER

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

[program:simulate_nbp]
command=${VENV_BIN}/python logger/utils/simulate_data.py --config test/NBP1406/simulate_NBP1406.yaml
directory=${INSTALL_ROOT}/openrvdas
autostart=false
autorestart=true
startretries=3
killasgroup=true
stderr_logfile=/var/log/openrvdas/simulate_nbp.stderr
stderr_logfile_maxbytes=10000000 ; 10M
stderr_logfile_maxbackups=100
user=$RVDAS_USER

[group:web]
programs=nginx,uwsgi

[group:openrvdas]
programs=logger_manager,cached_data_server

[group:simulate]
programs=simulate_nbp
EOF

    # Copy supervisor file into place
    sudo mkdir -p $SUPERVISOR_DIR
    sudo cp /tmp/openrvdas.ini $SUPERVISOR_FILE
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
###########################################################################
###########################################################################
# Start of actual script
###########################################################################
###########################################################################

# Read from the preferences file in $PREFERENCES_FILE, if it exists
set_default_variables

# Set OS_TYPE to either MacOS, CentOS or Ubuntu
get_os_type

# If we're on Linux, should run as root
if [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
    if [ "$(whoami)" != "root" ]; then
        echo "ERROR: installation script must be run as root."
        exit_gracefully
    fi
fi

# Set creation mask so that everything we install is, by default,
# world readable/executable.
umask 022

echo "#####################################################################"
echo "OpenRVDAS configuration script"

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
# Do they want to install/configure MySQL for use by DatabaseWriter, etc?
echo
echo "#####################################################################"
echo "MySQL or MariaDB, the CentOS replacement for MySQL, can be installed and"
echo "configured so that DatabaseWriter and DatabaseReader have something to"
echo "write to and read from."
echo
yes_no "Install and configure MySQL database? " $DEFAULT_INSTALL_MYSQL
INSTALL_MYSQL=$YES_NO_RESULT

if [ $INSTALL_MYSQL == 'yes' ]; then
    echo Will install/configure MySQL
    # Get current and new passwords for database
    echo "Root database password will be empty on initial installation. If this"
    echo "is the initial installation, hit "return" when prompted for root"
    echo "database password, otherwise enter the password you used during the"
    echo "initial installation."
    echo
    echo "Current database password for root \(hit return if this is the"
    read -p "initial installation)? " CURRENT_ROOT_DATABASE_PASSWORD
    read -p "New database password for root? ($CURRENT_ROOT_DATABASE_PASSWORD) " NEW_ROOT_DATABASE_PASSWORD
    NEW_ROOT_DATABASE_PASSWORD=${NEW_ROOT_DATABASE_PASSWORD:-$CURRENT_ROOT_DATABASE_PASSWORD}
else
    echo "Skipping MySQL installation/configuration"
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
# If we're installing MySQL/MariaDB
echo "#####################################################################"
if [ $INSTALL_MYSQL == 'yes' ]; then
    echo "Installing/configuring database"
    # Expect the following shell variables to be appropriately set:
    # RVDAS_USER - valid userid
    # RVDAS_DATABASE_PASSWORD - current rvdas user MySQL database password
    # NEW_ROOT_DATABASE_PASSWORD - new root password to use for MySQL
    # CURRENT_ROOT_DATABASE_PASSWORD - current root password for MySQL
    install_mysql
else
    echo "Skipping database setup"
fi

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
# INSTALL_MYSQL - set if MySQL is to be installed, unset otherwise
setup_python_packages

#########################################################################
#########################################################################
# Set up nginx
echo "#####################################################################"
echo "Setting up NGINX"
setup_nginx

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
echo
echo "#####################################################################"
echo "Setting up UWSGI"
# Expect the following shell variables to be appropriately set:
# HOSTNAME - name of host
# INSTALL_ROOT - path where openrvdas/ is
setup_uwsgi

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
chmod 755 ${INSTALL_ROOT}/openrvdas
chown -R ${RVDAS_USER} ${INSTALL_ROOT}/openrvdas
chgrp -R ${RVDAS_GROUP} ${INSTALL_ROOT}/openrvdas

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

echo
echo "#########################################################################"
echo "Restarting services: supervisor"
    # If we're on MacOS
    if [ $OS_TYPE == 'MacOS' ]; then
        sudo mkdir -p /usr/local/var/run/
        sudo chown $RVDAS_USER /usr/local/var/run
        sudo chgrp $RVDAS_GROUP /usr/local/var/run
        brew tap homebrew/services
        brew services restart supervisor

    # Linux
    elif [ $OS_TYPE == 'CentOS' ] || [ $OS_TYPE == 'Ubuntu' ]; then
        sudo mkdir -p /var/run/supervisor/
        sudo chgrp $RVDAS_GROUP /var/run/supervisor

        # CentOS/RHEL
        if [ $OS_TYPE == 'CentOS' ]; then
            systemctl enable supervisord
            systemctl restart supervisord
        else # Ubuntu/Debian
            systemctl enable supervisor
            systemctl restart supervisor
        fi

        # Previous installations used nginx and uwsgi as a service. We need to
        # disable them if they're running.
        echo Disabling legacy services
        systemctl stop nginx 2> /dev/null || echo "nginx not running"
        systemctl disable nginx 2> /dev/null || echo "nginx disabled"
        systemctl stop uwsgi 2> /dev/null || echo "uwsgi not running"
        systemctl disable uwsgi 2> /dev/null || echo "uwsgi disabled"
    fi


# Deactivate the virtual environment - we'll be calling all relevant
# binaries using their venv paths, so don't need it.
deactivate

echo
echo "#########################################################################"
echo "Installation complete - happy logging!"
echo
