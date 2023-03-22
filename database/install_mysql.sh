#!/bin/bash -e

# OpenRVDAS is available as open source under the MIT License at
#   https:/github.com/oceandatatools/openrvdas
#
# This script installs and configures MySQL to run with the OpenRVDAS
# database readers/writers.
#
# This script is somewhat rudimentary and has not been extensively
# tested. If it fails on some part of the installation, there is no
# guarantee that fixing the specific issue and simply re-running will
# produce the desired result.  Bug reports, and even better, bug
# fixes, will be greatly appreciated.

PREFERENCES_FILE='.install_mysql_preferences'

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
            elif [[ ! -z `grep "VERSION_ID=\"21" /etc/os-release` ]];then
                OS_VERSION=21
            elif [[ ! -z `grep "VERSION_ID=\"22" /etc/os-release` ]];then
                OS_VERSION=22
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
            else
                echo "Sorry - unknown Debian OS Version! - exiting."
                exit_gracefully
            fi

        # CentOS/RHEL
        elif [[ ! -z `grep "NAME=\"CentOS Stream\"" /etc/os-release` ]] || [[ ! -z `grep "NAME=\"CentOS Linux\"" /etc/os-release` ]] || [[ ! -z `grep "NAME=\"Red Hat Enterprise Linux Server\"" /etc/os-release` ]]  || [[ ! -z `grep "NAME=\"Red Hat Enterprise Linux Workstation\"" /etc/os-release` ]];then
            OS_TYPE=CentOS
            if [[ ! -z `grep "VERSION_ID=\"7" /etc/os-release` ]];then
                OS_VERSION=7
            elif [[ ! -z `grep "VERSION_ID=\"8" /etc/os-release` ]];then
                OS_VERSION=8
            elif [[ ! -z `grep "VERSION_ID=\"9" /etc/os-release` ]];then
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
    echo Recognizing OS type as $OS_TYPE
}

###########################################################################
###########################################################################
# Read any pre-saved default variables from file
function set_default_variables {
    # Defaults that will be overwritten by the preferences file, if it
    # exists.
    DEFAULT_INSTALL_ROOT=/opt
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


DEFAULT_INSTALL_ROOT=$INSTALL_ROOT
DEFAULT_RVDAS_USER=$RVDAS_USER

EOF
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

    # Get current and new passwords for database
    echo "Root database password will be empty on initial installation. If this"
    echo "is the initial installation, hit \"return\" when prompted for root"
    echo "database password, otherwise enter the password you used during the"
    echo "initial installation."
    echo
    read -p "Current database password for root? " CURRENT_ROOT_DATABASE_PASSWORD
    read -p "New database password for root? ($CURRENT_ROOT_DATABASE_PASSWORD) " NEW_ROOT_DATABASE_PASSWORD
    NEW_ROOT_DATABASE_PASSWORD=${NEW_ROOT_DATABASE_PASSWORD:-$CURRENT_ROOT_DATABASE_PASSWORD}

    read -p "Database password to use for user $RVDAS_USER? ($RVDAS_USER) " RVDAS_DATABASE_PASSWORD
    RVDAS_DATABASE_PASSWORD=${RVDAS_DATABASE_PASSWORD:-$RVDAS_USER}

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

[group:web]
programs=nginx,uwsgi

[group:openrvdas]
programs=logger_manager,cached_data_server

${SIMULATE_NBP_COMMENT}[group:simulate]
${SIMULATE_NBP_COMMENT}programs=simulate_nbp
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
echo "MySQL configuration script"

# Create user if they don't exist yet on Linux, but MacOS needs to
# user a pre-existing user, because creating a user is a pain.
echo
read -p "OpenRVDAS user? ($DEFAULT_RVDAS_USER) " RVDAS_USER
RVDAS_USER=${RVDAS_USER:-$DEFAULT_RVDAS_USER}

if [ $OS_TYPE == 'MacOS' ]; then
    RVDAS_GROUP=wheel
# If we're on Linux
else
    RVDAS_GROUP=$RVDAS_USER
fi
read -p "OpenRVDAS install root? ($DEFAULT_INSTALL_ROOT) " INSTALL_ROOT
INSTALL_ROOT=${INSTALL_ROOT:-$DEFAULT_INSTALL_ROOT}

#########################################################################
#########################################################################
echo "#####################################################################"
echo "MySQL or MariaDB, the CentOS replacement for MySQL, will be installed and"
echo "configured so that DatabaseWriter and DatabaseReader have something to"
echo "write to and read from."

#########################################################################
#########################################################################
# Save defaults in a preferences file for the next time we run.
save_default_variables

#########################################################################
#########################################################################
# If we're installing MySQL/MariaDB
echo "#####################################################################"
echo "Installing/configuring database"

install_mysql

# Deactivate the virtual environment - we'll be calling all relevant
# binaries using their venv paths, so don't need it.
deactivate

echo
echo "#########################################################################"
echo "Installation complete - happy logging!"
echo
