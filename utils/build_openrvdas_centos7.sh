#!/bin/bash -e

# This script is designed to be run as root. It should take a clean CentOS 7
# installation and install and configure all the components to run the full
# OpenRVDAS system.

# Once this script has completed and the machine has been rebooted,
# you should be able to run "service openrvdas start" to have the
# system up and running. We don't want to make it start automatically
# by default, as it can eat away at both machine computation and
# bandwidth budgets.

# OpenRVDAS is available as open source under the MIT License at
#   https:/github.com/oceandatatools/openrvdas

# This script is VERY rudimentary and has not been extensively tested. If it
# fails on some part of the installation, there is no guarantee that fixing
# the specific issue and simply re-running will produce the desired result.
# Bug reports, and even better, bug fixes, will be greatly appreciated.

DEFAULT_HOSTNAME=$HOSTNAME
DEFAULT_INSTALL_ROOT=/opt
#DEFAULT_HTTP_PROXY=proxy.lmg.usap.gov:3128 #$HTTP_PROXY
DEFAULT_HTTP_PROXY=$http_proxy

DEFAULT_OPENRVDAS_REPO=https://github.com/oceandatatools/openrvdas
DEFAULT_OPENRVDAS_BRANCH=master

DEFAULT_RVDAS_USER=rvdas

if [ "$(whoami)" != "root" ]; then
  echo "ERROR: installation script must be run as root."
  return -1 2> /dev/null || exit -1  # terminate correctly if sourced/bashed
fi

echo "############################################################################"
echo OpenRVDAS configuration script

read -p "Name to assign to host ($DEFAULT_HOSTNAME)? " HOSTNAME
HOSTNAME=${HOSTNAME:-$DEFAULT_HOSTNAME}
echo "Hostname will be '$HOSTNAME'"

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

# Create user if they don't exist yet
read -p "OpenRVDAS user to create? ($DEFAULT_RVDAS_USER) " RVDAS_USER
RVDAS_USER=${RVDAS_USER:-$DEFAULT_RVDAS_USER}
echo Checking if user $RVDAS_USER exists yet
if id -u $RVDAS_USER > /dev/null; then
  echo User exists, skipping
else
  echo Creating $RVDAS_USER
  adduser $RVDAS_USER
  passwd $RVDAS_USER
  usermod -a -G tty $RVDAS_USER
fi

# Get current and new passwords for database
echo
echo Root database password will be empty on initial installation. If this
echo is the initial installation, hit "return" when prompted for root
echo database password, otherwise enter the password you used during the
echo initial installation.
echo
echo Current database password for root \(hit return if this is the
read -p "initial installation)? " CURRENT_ROOT_DATABASE_PASSWORD
read -p "New database password for root? ($CURRENT_ROOT_DATABASE_PASSWORD) " NEW_ROOT_DATABASE_PASSWORD
NEW_ROOT_DATABASE_PASSWORD=${NEW_ROOT_DATABASE_PASSWORD:-$CURRENT_ROOT_DATABASE_PASSWORD}
read -p "Database password to use for user $RVDAS_USER? ($RVDAS_USER) " RVDAS_DATABASE_PASSWORD
RVDAS_DATABASE_PASSWORD=${RVDAS_DATABASE_PASSWORD:-$RVDAS_USER}

echo
echo "############################################################################"
echo The OpenRVDAS server can be configured to start on boot. If you wish this
echo to happen, it will be run/monitored by the supervisord service using the
echo configuration file in /etc/supervisord.d/openrvdas.ini.
echo
echo If you do not wish it to start automatically, it may still be run manually
echo from the command line or started via supervisor by running supervisorctl
echo and starting processes logger_manager and cached_data_server.
echo
while true; do
    read -p "Do you wish to start the OpenRVDAS server on boot? " yn
    case $yn in
        [Yy]* )
            START_OPENRVDAS_AS_SERVICE=True
            echo Will enable openrvdas server run on boot.
            break;;
        [Nn]* )
            break;;
        * ) echo "Please answer yes or no.";;
    esac
done

# Convenient way of commenting out stuff
if [ 0 -eq 1 ]; then
  Commented out stuff goes here
fi

# Set creation mask so that everything we install is, by default,
# world readable/executable.
umask 022

# Create openrvdas log and tmp directories
mkdir -p /var/log/openrvdas /var/tmp/openrvdas
chown $RVDAS_USER /var/log/openrvdas /var/tmp/openrvdas

# Set hostname
echo "############################################################################"
echo Setting hostname...
hostnamectl set-hostname $HOSTNAME
echo "HOSTNAME=$HOSTNAME" > /etc/sysconfig/network

# Install yum stuff
echo "############################################################################"
echo Installing required packages from yum...
yum install -y deltarpm
yum install -y epel-release
yum -y update

yum install -y socat git nginx sqlite-devel readline-devel \
    wget gcc zlib-devel openssl-devel \
    mariadb-server mariadb-devel mariadb-libs \
    python3 python36-devel python36-pip firewalld supervisor
#[ -e /usr/bin/python3 ] || ln -s /usr/bin/python36 /usr/bin/python3

echo "############################################################################"
echo Enabling Mariadb \(MySQL replacement in CentOS 7\)...
service mariadb restart              # to manually start db server
systemctl enable mariadb.service     # to make it start on boot

# Set up OpenRVDAS
echo "############################################################################"
echo Fetching and setting up OpenRVDAS code...

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

# Set up virtual env and python-dependent code (Django and uWSGI, etc)
echo "############################################################################"

echo Installing virtual environment for Django, uWSGI and other Python-dependent packages.

# Set up virtual environment
#pip3 install virtualenv
VENV_PATH=$INSTALL_ROOT/openrvdas/venv
python3 -m venv $VENV_PATH
source $VENV_PATH/bin/activate  # activate virtual environment

# Inside the venv, python *is* the right version, right?
python3 -m pip install --upgrade pip
pip3 install \
  Django==2.1 \
  pyserial \
  uwsgi \
  websockets \
  PyYAML \
  parse \
  mysqlclient \
  mysql-connector \
  psutil
  # diskcache

echo "############################################################################"
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
mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD <<EOF > /dev/null || echo table \"data\" appears to already exist - no problem
create database data character set utf8;
EOF
#mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD <<EOF > /dev/null || echo table \"openrvdas\" appears to already exist - no problem
#create database openrvdas character set utf8;
#EOF

mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD <<EOF
GRANT ALL PRIVILEGES ON data.* TO $RVDAS_USER@localhost IDENTIFIED BY '$RVDAS_DATABASE_PASSWORD' WITH GRANT OPTION;
#GRANT ALL PRIVILEGES ON openrvdas.* TO $RVDAS_USER@localhost IDENTIFIED BY '$RVDAS_DATABASE_PASSWORD' WITH GRANT OPTION;

#GRANT ALL PRIVILEGES ON test_openrvdas.* TO '$RVDAS_USER'@'localhost';
#GRANT ALL PRIVILEGES ON test_openrvdas.* TO 'test'@'localhost' identified by 'test';

GRANT ALL PRIVILEGES ON test.* TO $RVDAS_USER@localhost IDENTIFIED BY '$RVDAS_DATABASE_PASSWORD' WITH GRANT OPTION;
GRANT ALL PRIVILEGES ON test.* TO test@localhost IDENTIFIED BY 'test' WITH GRANT OPTION;
FLUSH PRIVILEGES;
EOF
echo Done setting up database

# Set up nginx
echo "############################################################################"
echo Setting up NGINX
# Disable because we're going to run it via supervisor
systemctl stop nginx
systemctl disable nginx # NGINX seems to be enabled by default?

[ -e /etc/nginx/sites-available ] || mkdir /etc/nginx/sites-available
[ -e /etc/nginx/sites-enabled ] || mkdir /etc/nginx/sites-enabled

# We need to add a couple of lines to not quite the end of nginx.conf,
# so do a bit of hackery: chop off the closing "}" with head, append
# the lines we need and a new closing "}" into a temp file, then copy back.
if grep -q "/etc/nginx/sites-enabled/" /etc/nginx/nginx.conf; then
  echo NGINX sites-available already registered. Skipping...
else
  head --lines=-2 /etc/nginx/nginx.conf > /tmp/nginx.conf
  cat >> /tmp/nginx.conf <<EOF
     include /etc/nginx/sites-enabled/*.conf;
     server_names_hash_bucket_size 64;
}
EOF
  mv -f /tmp/nginx.conf /etc/nginx/nginx.conf
  echo Done setting up NGINX
fi

#cat > /etc/profile.d/openrvdas.sh <<EOF
#export PYTHONPATH=$PYTHONPATH:${INSTALL_ROOT}/openrvdas
#export PATH=$PATH:${INSTALL_ROOT}/openrvdas/logger/listener
#EOF

# Set up Django database
echo "#########################################################################"
echo Initializing Django database...
cd ${INSTALL_ROOT}/openrvdas
cp django_gui/settings.py.dist django_gui/settings.py
sed -i -e "s/'USER': 'rvdas'/'USER': '${RVDAS_USER}'/g" django_gui/settings.py
sed -i -e "s/'PASSWORD': 'rvdas'/'PASSWORD': '${RVDAS_DATABASE_PASSWORD}'/g" django_gui/settings.py

cp database/settings.py.dist database/settings.py
sed -i -e "s/DEFAULT_DATABASE_USER = 'rvdas'/DEFAULT_DATABASE_USER = '${RVDAS_USER}'/g" database/settings.py
sed -i -e "s/DEFAULT_DATABASE_PASSWORD = 'rvdas'/DEFAULT_DATABASE_PASSWORD = '${RVDAS_DATABASE_PASSWORD}'/g" database/settings.py

cp display/js/widgets/settings.js.dist \
   display/js/widgets/settings.js
sed -i -e "s/localhost/${HOSTNAME}/g" display/js/widgets/settings.js

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

# Bass-ackwards way of creating superuser $RVDAS_USER, as the createsuperuser
# command won't work from a script
echo "from django.contrib.auth.models import User; User.objects.filter(email='${RVDAS_USER}@example.com').delete(); User.objects.create_superuser('${RVDAS_USER}', '${RVDAS_USER}@example.com', '${RVDAS_DATABASE_PASSWORD}')" | python3 manage.py shell

# Connect uWSGI with our project installation
echo "############################################################################"
echo Creating OpenRVDAS-specific uWSGI files
cp /etc/nginx/uwsgi_params $INSTALL_ROOT/openrvdas/django_gui

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
ln -sf ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_nginx.conf /etc/nginx/sites-enabled

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
[ -e /etc/uwsgi/vassals ] || mkdir -p /etc/uwsgi/vassals
ln -sf ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_uwsgi.ini \
      /etc/uwsgi/vassals/

# Make everything accessible to nginx
chmod 755 ${INSTALL_ROOT}/openrvdas
chown -R ${RVDAS_USER} ${INSTALL_ROOT}/openrvdas
chgrp -R ${RVDAS_USER} ${INSTALL_ROOT}/openrvdas

## Make uWSGI run on boot - No, we will start through supervisord
#systemctl enable uwsgi.service
#service uwsgi start

## Make nginx run on boot - No, we will start through supervisord
#systemctl enable nginx.service
#service nginx start

echo "############################################################################"
echo Setting up openrvdas service with supervisord
if [ -z $START_OPENRVDAS_AS_SERVICE ]; then
    echo Openrvdas will *not* start on boot. To start it, run supervisorctl
    echo and start processes logger_manager and cached_data_server.
    SUPERVISOR_AUTOSTART=false
else
    echo Openrvdas will start on boot
    SUPERVISOR_AUTOSTART=true
fi

VENV_BIN=${INSTALL_ROOT}/openrvdas/venv/bin

cat > /etc/supervisord.d/openrvdas.ini <<EOF
; First, override the default socket permissions to allow user
; $RVDAS_USER to run supervisorctl
[unix_http_server]
file=/var/run/supervisor/supervisor.sock   ; (the path to the socket file)
chmod=0770                      ; socket file mode (default 0700)
chown=nobody:${RVDAS_USER}

[inet_http_server]
port=*:9001
username=${RVDAS_USER}
password=${RVDAS_USER}

; The scripts we're going to run
[program:nginx]
command=/usr/sbin/nginx -g 'daemon off;'
directory=${INSTALL_ROOT}/openrvdas
autostart=$SUPERVISOR_AUTOSTART
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/nginx.err.log
stdout_logfile=/var/log/openrvdas/nginx.out.log
;user=$RVDAS_USER

[program:uwsgi]
command=${VENV_BIN}/uwsgi /${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_uwsgi.ini --thunder-lock --enable-threads
stopsignal=INT
directory=${INSTALL_ROOT}/openrvdas
autostart=$SUPERVISOR_AUTOSTART
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/uwsgi.err.log
stdout_logfile=/var/log/openrvdas/uwsgi.out.log
user=$RVDAS_USER

[program:cached_data_server]
command=${VENV_BIN}/python server/cached_data_server.py --port 8766 --disk_cache /var/tmp/openrvdas/disk_cache --max_records 8640 -v
directory=${INSTALL_ROOT}/openrvdas
autostart=$SUPERVISOR_AUTOSTART
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/cached_data_server.err.log
stdout_logfile=/var/log/openrvdas/cached_data_server.out.log
user=$RVDAS_USER

[program:logger_manager]
command=${VENV_BIN}/python server/logger_manager.py --database django --no-console --data_server_websocket :8766  --start_supervisor_in /var/tmp/openrvdas/supervisor -v
environment=PATH="${VENV_BIN}:/usr/bin:/usr/local/bin"
directory=${INSTALL_ROOT}/openrvdas
autostart=$SUPERVISOR_AUTOSTART
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/logger_manager.err.log
stdout_logfile=/var/log/openrvdas/logger_manager.out.log
user=$RVDAS_USER

[program:simulate_nbp]
command=${VENV_BIN}/python logger/utils/simulate_data.py --config test/NBP1406/simulate_NBP1406.yaml
directory=${INSTALL_ROOT}/openrvdas
autostart=false
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/simulate_nbp.err.log
stdout_logfile=/var/log/openrvdas/simulate_nbp.out.log
user=$RVDAS_USER

[program:simulate_skq]
command=${VENV_BIN}/python logger/utils/simulate_data.py --config test/SKQ201822S/simulate_SKQ201822S.yaml
directory=${INSTALL_ROOT}/openrvdas
autostart=false
autorestart=true
startretries=3
stderr_logfile=/var/log/openrvdas/simulate_skq.err.log
stdout_logfile=/var/log/openrvdas/simulate_skq.out.log
user=$RVDAS_USER

;; Uncomment the following command block if you've installed InfluxDB
;; and want it to run as a service.
;[program:influxdb]
;command=database/influxdb/bin/influxd --reporting-disabled
;directory=${INSTALL_ROOT}/openrvdas
;autostart=$SUPERVISOR_AUTOSTART
;autorestart=true
;startretries=3
;stderr_logfile=/var/log/openrvdas/influxdb.err.log
;stdout_logfile=/var/log/openrvdas/influxdb.out.log
;user=$RVDAS_USER

[group:web]
programs=nginx,uwsgi

[group:openrvdas]
programs=logger_manager,cached_data_server

[group:simulate]
programs=simulate_nbp,simulate_skq
EOF

# Set permissions
echo "############################################################################"
echo Setting SELINUX permissions and firewall ports
echo This could take a while...

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

firewall-cmd -q --permanent --add-port=80/tcp > /dev/null
firewall-cmd -q --permanent --add-port=8000/tcp > /dev/null
firewall-cmd -q --permanent --add-port=8001/tcp > /dev/null
firewall-cmd -q --permanent --add-port=8002/tcp > /dev/null

# Supervisord ports - 9001 is default system-wide supervisor
# and 9002 is the captive supervisor that logger_manager uses.
firewall-cmd -q --permanent --add-port=9001/tcp > /dev/null
firewall-cmd -q --permanent --add-port=9002/tcp > /dev/null

# Websocket ports
firewall-cmd -q --permanent --add-port=8765/tcp > /dev/null # status
firewall-cmd -q --permanent --add-port=8766/tcp > /dev/null # data

# Our favorite UDP port for network data
firewall-cmd -q --permanent --add-port=6224/udp > /dev/null
firewall-cmd -q --permanent --add-port=6225/udp > /dev/null

# For unittest access
firewall-cmd -q --permanent --add-port=8000/udp > /dev/null
firewall-cmd -q --permanent --add-port=8001/udp > /dev/null
firewall-cmd -q --permanent --add-port=8002/udp > /dev/null
firewall-cmd -q --reload > /dev/null
echo Done setting SELINUX permissions

#echo "############################################################################"
#while true; do
#    read -p "Do you wish to install Redis? " yn
#    case $yn in
#        [Yy]* )
#            yum install -y redis;
#            pip3.6 install redis;
#
#            while true; do
#                read -p "Do you wish to start a Redis server on boot? " ynb
#                case $ynb in
#                    [Yy]* )
#                        systemctl start redis
#                        systemctl enable redis.service;
#                        break;;
#                    [Nn]* )
#                        break;;
#                    * ) echo "Please answer yes or no.";;
#                esac
#            done
#            break;;
#        [Nn]* )
#            break;;
#        * ) echo "Please answer yes or no.";;
#    esac
#done

echo "#########################################################################"
echo Restarting services: supervisor
mkdir -p /var/run/supervisor/
chgrp $RVDAS_USER /var/run/supervisor
systemctl enable supervisord
systemctl restart supervisord # nginx uwsgi are now started by supervisor

# Previous installations used nginx and uwsgi as a service. We need to
# disable them if they're running.
echo Disabling legacy services
systemctl stop nginx 2> /dev/null || echo nginx not running
systemctl disable nginx 2> /dev/null || echo nginx disabled
systemctl stop uwsgi 2> /dev/null || echo uwsgi not running
systemctl disable uwsgi 2> /dev/null || echo uwsgi disabled

# Deactivate the virtual environment - we'll be calling all relevant
# binaries using their venv paths, so don't need it.
deactivate

echo "#########################################################################"
echo Installation complete - happy logging!
echo
