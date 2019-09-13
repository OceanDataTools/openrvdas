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
#   https:/github.com/davidpablocohn/openrvdas

# This script is VERY rudimentary and has not been extensively tested. If it
# fails on some part of the installation, there is no guarantee that fixing
# the specific issue and simply re-running will produce the desired result.
# Bug reports, and even better, bug fixes, will be greatly appreciated.

DEFAULT_HOSTNAME=$HOSTNAME
DEFAULT_INSTALL_ROOT=/opt
#DEFAULT_HTTP_PROXY=proxy.lmg.usap.gov:3128 #$HTTP_PROXY
DEFAULT_HTTP_PROXY=$http_proxy

DEFAULT_OPENRVDAS_REPO=https://github.com/davidpablocohn/openrvdas
DEFAULT_OPENRVDAS_BRANCH=master

DEFAULT_RVDAS_USER=rvdas

if [ "$(whoami)" != "root" ]; then
  echo "ERROR: installation script must be run as root."
  return -1 2> /dev/null || exit -1  # terminate correctly if sourced/bashed
fi

echo "############################################################################"
echo OpenRVDAS configuration script
while true; do
    read -p "Do you wish to continue? " yn
    case $yn in
        [Yy]* ) break;;
        [Nn]* ) exit;;
        * ) echo "Please answer yes or no.";;
    esac
done

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
  #passwd $RVDAS_USER
  usermod -a -G tty $RVDAS_USER
fi

# Get current and new passwords for database
echo
read -p "Database password to use for $RVDAS_USER? ($RVDAS_USER) " RVDAS_DATABASE_PASSWORD
RVDAS_DATABASE_PASSWORD=${RVDAS_DATABASE_PASSWORD:-$RVDAS_USER}
read -p "Current database password for root? (if one exists - hit return if not) " CURRENT_ROOT_DATABASE_PASSWORD
read -p "New database password for root? ($CURRENT_ROOT_DATABASE_PASSWORD) " NEW_ROOT_DATABASE_PASSWORD
NEW_ROOT_DATABASE_PASSWORD=${NEW_ROOT_DATABASE_PASSWORD:-$CURRENT_ROOT_DATABASE_PASSWORD}

echo
echo "############################################################################"
echo The OpenRVDAS server can be configured to start on boot. Otherwise
echo you will need to either run it manually from a terminal \(by running
echo 'server/logger_manager.py' from the openrvdas base directory\) or
echo start as a service \('service openrvdas start'\).
echo
while true; do
    read -p "Do you wish to start the OpenRVDAS server on boot? " yn
    case $yn in
        [Yy]* )
            START_OPENRVDAS_AS_SERVICE=True
            echo Enabled openrvdas server run on boot.
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

# Set hostname
echo "############################################################################"
echo Setting hostname...
hostnamectl set-hostname $HOSTNAME
echo $HOSTNAME > /etc/hostname
ETC_HOSTS_LINE="127.0.1.1	$HOSTNAME"
if grep -q "$ETC_HOSTS_LINE" /etc/hosts ; then
  echo Hostname already in /etc/hosts
else
  echo "$ETC_HOSTS_LINE" >> /etc/hosts
fi

# Install apt packages
echo "#########################################################################"
echo Installing required packages...
apt-get update

apt install -y socat git nginx python3-dev python3-pip libreadline-dev \
    mysql-server mysql-common mysql-client libmysqlclient-dev libsqlite3-dev \
    openssh-server

# Install database stuff and set up as service.
echo "#########################################################################"
echo Setting up MySQL database tables and permissions
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

# Set up as a service
update-rc.d mysql defaults

echo "#########################################################################"
echo Setting up database users
mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD <<EOF 
drop user if exists 'test'@'localhost'; 
create user 'test'@'localhost' identified by 'test';

drop user if exists 'rvdas'@'localhost';
create user '$RVDAS_USER'@'localhost' identified by '$RVDAS_DATABASE_PASSWORD';

create database if not exists data character set utf8;
GRANT ALL PRIVILEGES ON data.* TO '$RVDAS_USER'@'localhost';

create database if not exists openrvdas character set utf8;
GRANT ALL PRIVILEGES ON openrvdas.* TO '$RVDAS_USER'@'localhost';

create database if not exists test character set utf8;
GRANT ALL PRIVILEGES ON test.* TO '$RVDAS_USER'@'localhost';
GRANT ALL PRIVILEGES ON test.* TO 'test'@'localhost' identified by 'test';

create database if not exists test_$RVDAS_USER character set utf8;
GRANT ALL PRIVILEGES ON test_$RVDAS_USER.* TO '$RVDAS_USER'@'localhost';
GRANT ALL PRIVILEGES ON test_$RVDAS_USER.* TO 'test'@'localhost' identified by 'test';

flush privileges;
\q
EOF
echo Done setting up database

# Django and uWSGI
echo "############################################################################"

echo Installing Django, uWSGI and other Python-dependent packages
export PATH=/usr/bin:/usr/local/bin:$PATH
/usr/bin/pip3 install --upgrade pip &> /dev/null || echo Upgrading old pip if it's there
#/usr/bin/env pip install --upgrade pip || echo Upgrading new pip if it\'s there

/usr/bin/env pip install Django==2.0 pyserial uwsgi websockets PyYAML \
       parse mysqlclient mysql-connector
# uWSGI configuration
#Following instructions in https://www.tecmint.com/create-new-service-units-in-systemd/

echo "#########################################################################"
echo Configuring uWSGI as service

# Create uwsgi.service file
cat > /etc/systemd/system/uwsgi.service <<EOF
[Unit]
Description = Run uWSGI as a daemon
After = network.target

[Service]
ExecStart = /etc/uwsgi/scripts/start_uwsgi_daemon.sh
RemainAfterExit=true
ExecStop = /etc/uwsgi/scripts/top_uwsgi_daemon.sh

[Install]
WantedBy = multi-user.target
EOF

# Create uWSGI start/stop scripts
[ -e /etc/uwsgi/scripts ] || mkdir -p /etc/uwsgi/scripts
cat > /etc/uwsgi/scripts/start_uwsgi_daemon.sh <<EOF
#!/bin/bash
# Start uWSGI as a daemon; installed as service
/usr/local/bin/uwsgi \
  --emperor /etc/uwsgi/vassals \
  --uid rvdas --gid rvdas \
  --pidfile /etc/uwsgi/process.pid \
  --daemonize /var/log/uwsgi-emperor.log
EOF

cat > /etc/uwsgi/scripts/stop_uwsgi_daemon.sh <<EOF
#!/bin/bash
/usr/local/bin/uwsgi --stop /etc/uwsgi/process.pid
EOF

chmod 755 /etc/uwsgi/scripts/start_uwsgi_daemon.sh /etc/uwsgi/scripts/stop_uwsgi_daemon.sh

# Set up nginx
echo "############################################################################"
echo Setting up NGINX
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

# Set up openrvdas
echo "############################################################################"
echo Fetching and setting up OpenRVDAS code...
cd $INSTALL_ROOT

if [ -e openrvdas ]; then
  cd openrvdas
  git checkout $OPENRVDAS_BRANCH
  git pull
else
  git clone -b $OPENRVDAS_BRANCH $OPENRVDAS_REPO
  cd openrvdas
fi

cat > /etc/profile.d/openrvdas.sh <<EOF
export PYTHONPATH=$PYTHONPATH:${INSTALL_ROOT}/openrvdas
export PATH=$PATH:${INSTALL_ROOT}/openrvdas/logger/listener
EOF

echo Initializing OpenRVDAS database...
cp django_gui/settings.py.dist django_gui/settings.py
sed -i -e "s/'USER': 'rvdas'/'USER': '${RVDAS_USER}'/g" django_gui/settings.py
sed -i -e "s/'PASSWORD': 'rvdas'/'PASSWORD': '${RVDAS_DATABASE_PASSWORD}'/g" django_gui/settings.py

cp database/settings.py.dist database/settings.py
sed -i -e "s/DEFAULT_DATABASE_USER = 'rvdas'/DEFAULT_DATABASE_USER = '${RVDAS_USER}'/g" database/settings.py
sed -i -e "s/DEFAULT_DATABASE_PASSWORD = 'rvdas'/DEFAULT_DATABASE_PASSWORD = '${RVDAS_DATABASE_PASSWORD}'/g" database/settings.py

cp widgets/static/js/widgets/settings.js.dist \
   widgets/static/js/widgets/settings.js
sed -i -e "s/localhost/${HOSTNAME}/g" widgets/static/js/widgets/settings.js

python3 manage.py makemigrations django_gui
python3 manage.py migrate
python3 manage.py collectstatic --no-input --clear --link
chmod -R og+rX static

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

    location /static {
        alias ${INSTALL_ROOT}/openrvdas/static; # project static files
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
# the base directory from which bin/python is available
# Do an ln -s bin/python3 bin/python in this dir!!!
home            = /usr

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
chown -R rvdas ${INSTALL_ROOT}/openrvdas
chgrp -R rvdas ${INSTALL_ROOT}/openrvdas

# Make uWSGI run on boot
systemctl enable uwsgi.service
service uwsgi start

# Make nginx run on boot:
systemctl enable nginx.service
service nginx start

echo "############################################################################"
echo Installing OpenRVDAS server as a service
cat > /etc/systemd/system/openrvdas.service <<EOF
[Unit]
Description = Run openrvdas/server/logger_manager.py as service
After = network.target

[Service]
ExecStart = ${INSTALL_ROOT}/openrvdas/scripts/start_openrvdas.sh
ExecStop = ${INSTALL_ROOT}/openrvdas/scripts/stop_openrvdas.sh

[Install]
WantedBy = multi-user.target
EOF

[ -e ${INSTALL_ROOT}/openrvdas/scripts ] || mkdir -p ${INSTALL_ROOT}/openrvdas/scripts
cat > ${INSTALL_ROOT}/openrvdas/scripts/start_openrvdas.sh <<EOF
#!/bin/bash
# Start openrvdas servers as service
OPENRVDAS_LOG_DIR=/var/log/openrvdas
OPENRVDAS_LOGFILE=\$OPENRVDAS_LOG_DIR/openrvdas.log
DATA_SERVER_LOGFILE=\$OPENRVDAS_LOG_DIR/cached_data_server.log

mkdir -p \$OPENRVDAS_LOG_DIR
chown $RVDAS_USER \$OPENRVDAS_LOG_DIR
chgrp $RVDAS_USER \$OPENRVDAS_LOG_DIR

DATA_SERVER_UDP_PORT=6225
DATA_SERVER_WEBSOCKET_PORT=8766
DATA_SERVER_LISTEN_ON_UDP=
DATA_SERVER_WEBSOCKET=:\$DATA_SERVER_WEBSOCKET_PORT

# Comment out line below to have data server we start *not* listen on UDP       
#DATA_SERVER_LISTEN_ON_UDP='--udp \$DATA_SERVER_UDP_PORT'  

# Run cached data server in background                                          
sudo -u $RVDAS_USER -- sh -c "cd ${INSTALL_ROOT}/openrvdas;/usr/bin/python3 ${INSTALL_ROOT}/openrvdas/server/cached_data_server.py --port \$DATA_SERVER_WEBSOCKET_PORT \$DATA_SERVER_LISTEN_ON_UDP  2>&1 | tee \$DATA_SERVER_LOGFILE &"

# Run logger manager in foreground                                              
sudo -u $RVDAS_USER -- sh -c "cd ${INSTALL_ROOT}/openrvdas;/usr/bin/python3 ${INSTALL_ROOT}/openrvdas/server/logger_manager.py --database django --no-console -v --stderr_file \$OPENRVDAS_LOGFILE --data_server_websocket \$DATA_SERVER_WEBSOCKET"
EOF

cat > ${INSTALL_ROOT}/openrvdas/scripts/stop_openrvdas.sh <<EOF
#!/bin/bash
USER=rvdas
sudo -u $RVDAS_USER sh -c 'pkill -f "/usr/bin/python3 server/cached_data_server.py"'
sudo -u $RVDAS_USER sh -c 'pkill -f "/usr/bin/python3 server/logger_manager.py"'
EOF

chmod 755 ${INSTALL_ROOT}/openrvdas/scripts/start_openrvdas.sh ${INSTALL_ROOT}/openrvdas/scripts/stop_openrvdas.sh

# Enable openrvdas as a service
echo "############################################################################"
[ -z $START_OPENRVDAS_AS_SERVICE ] ||  echo Enabling openrvdas as a service
[ -z $START_OPENRVDAS_AS_SERVICE ] ||  systemctl enable openrvdas.service;

#echo "############################################################################"
#while true; do
#    read -p "Do you wish to install Redis? " yn
#    case $yn in
#        [Yy]* )
#            apt-get install -y redis-server;
#            pip3 install redis;
#
#            while true; do
#                read -p "Do you wish to start a Redis server on boot? " ynb
#                case $ynb in
#                    [Yy]* )
#                        systemctl start redis
#                        #systemctl enable redis.service;
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
echo "#########################################################################"
echo Installation complete.
echo 
echo To manually run server, go to install directory and run logger_manager.py
echo 
echo '  cd $INSTALL_ROOT/openrvdas'
echo '  python3 server/logger_manager.py --database django -v'
echo 
echo "#########################################################################"
echo Finished installation and configuration. You must reboot before some
echo changes take effect.
while true; do
    read -p "Do you wish to reboot now? " yn
    case $yn in
        [Yy]* ) reboot now; break;;
        [Nn]* ) break;;
        * ) echo "Please answer yes or no.";;
    esac
done

