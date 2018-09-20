#!/bin/bash

# This script is designed to be run as root. It should take a clean
# Ubuntu 16.04 installation and install and configure all the components
# to run the full OpenRVDAS system.

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

DEFAULT_HOSTNAME=openrvdas
DEFAULT_INSTALL_ROOT=/opt

DEFAULT_OPENRVDAS_REPO=http://github.com/davidpablocohn/openrvdas
DEFAULT_OPENRVDAS_BRANCH=master

DEFAULT_RVDAS_USER=rvdas

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

read -p "Repository to install from? ($DEFAULT_OPENRVDAS_REPO) " OPENRVDAS_REPO
OPENRVDAS_REPO=${OPENRVDAS_REPO:-$DEFAULT_OPENRVDAS_REPO}

read -p "Repository branch to install? ($DEFAULT_OPENRVDAS_BRANCH) " OPENRVDAS_BRANCH
OPENRVDAS_BRANCH=${OPENRVDAS_BRANCH:-$DEFAULT_OPENRVDAS_BRANCH}
echo "Will install from repository '$OPENRVDAS_REPO', branch '$OPENRVDAS_BRANCH'"

read -p "OpenRVDAS user to create? ($DEFAULT_RVDAS_USER) " RVDAS_USER
RVDAS_USER=${RVDAS_USER:-$DEFAULT_RVDAS_USER}

# Convenient way of commenting out stuff
if [ 0 -eq 1 ]; then
  Commented out stuff goes here
fi

# Create user
echo Checking if user $RVDAS_USER exists yet
if id -u $RVDAS_USER > /dev/null; then
  echo User exists, skipping
else
  echo Creating $RVDAS_USER
  useradd $RVDAS_USER
  passwd $RVDAS_USER
  usermod -a -G tty $RVDAS_USER
fi

# Set hostname
echo "#########################################################################"
echo Setting hostname...
hostname $HOSTNAME
echo $HOSTNAME > /etc/hostname
ETC_HOSTS_LINE="127.0.1.1	$HOSTNAME"
if grep -q "$ETC_HOSTS_LINE" /etc/hosts ; then
  echo Hostname already in /etc/hosts
else
  echo "$ETC_HOSTS_LINE" >> /etc/hosts
fi

# If openssh-server not installed, do that
if dpkg -l | grep -q openssh-server ; then
  echo openssh-server already installed
else
  echo Installing openssh-server
  apt install -Y openssh-server
  systemctl restart ssh
fi

# Install apt packages
echo "#########################################################################"
echo Installing required packages...
apt-get install -y socat git nginx libreadline-dev libmysqlclient-dev \
        libsqlite3-dev 

# Install database stuff and set up as service.
echo "#########################################################################"
MYSQL_IS_UP=$(pgrep mysql | wc -l);
if [ "$MYSQL_IS_UP" -ne 1 ];
then
  echo Installing MySQL and configuring as service...
  read -p "Hit any key to continue. " any_key
  apt-get install -y mysql-server
  mysql_secure_installation
else
  echo MySQL already installed and running...
fi
update-rc.d mysql defaults

echo "#########################################################################"
echo Setting up database tables and permissions
echo
echo Creating database user "$RVDAS_USER"
read -p "Database password to use for $RVDAS_USER? ($RVDAS_USER) " RVDAS_PASSWORD
RVDAS_PASSWORD=${RVDAS_PASSWORD:-$RVDAS_USER}

echo Please enter MySQL root password again to continue configuration:
mysql -u root -p <<EOF 
drop user if exists 'test'@'localhost'; 
create user 'test'@'localhost' identified by 'test';

drop user if exists 'rvdas'@'localhost';
create user '$RVDAS_USER'@'localhost' identified by '$RVDAS_PASSWORD';

create database if not exists data character set utf8;
GRANT ALL PRIVILEGES ON data.* TO '$RVDAS_USER'@'localhost';

create database if not exists openrvdas character set utf8;
GRANT ALL PRIVILEGES ON openrvdas.* TO '$RVDAS_USER'@'localhost';

create database if not exists test character set utf8;
GRANT ALL PRIVILEGES ON test.* TO '$RVDAS_USER'@'localhost';
GRANT ALL PRIVILEGES ON test.* TO 'test'@'localhost' identified by 'test';

flush privileges;
\q
EOF
echo Done setting up database

# Install Python
echo "#########################################################################"
#PYTHON_VERSION=3.5.2
PYTHON_VERSION=3.6.3
PYTHON_NAME=Python-${PYTHON_VERSION}
if [[ `python3 -V` == "Python $PYTHON_VERSION" ]]; then
    echo Already have $PYTHON_NAME - skipping installation
else
  echo Installing $PYTHON_NAME
  while true; do
    read -p "Run Python optimizations? " yn
    case $yn in
        [Yy]* ) PYTHON_OPT=" --enable-optimizations"; break;;
        [Nn]* ) PYTHON_OPT=""; break;;
        * ) echo "Please answer yes or no.";;
    esac
  done

  apt-get install -y build-essential libssl-dev zlib1g-dev libbz2-dev \
          libsqlite3-dev python3-dev python3-pip python3-openssl
  
  cd /tmp
  if [ ! -e /tmp/${PYTHON_NAME}.tgz ]; then
    echo Fetching ${PYTHON_NAME}
    wget https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_NAME}.tgz
  fi
  if [ ! -e /tmp/${PYTHON_NAME} ]; then
    echo Unpacking Python
    tar xzf ${PYTHON_NAME}.tgz
  fi
  echo Configuring and building Python
  cd ${PYTHON_NAME}
  ./configure $PYTHON_OPT --enable-loadable-sqlite-extensions
  make install
  ln -sf /usr/local/bin/python3 /usr/local/bin/python
  echo Done making Python
fi

# Django and uWSGI
echo "#########################################################################"
echo Installing Django, uWSGI and other Python-dependent packages
#pip3 install --upgrade pip
pip3 install Django==2.0 pyserial uwsgi websockets \
             mysqlclient mysql-connector==2.1.6

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
ExecStart = /root/scripts/start_uwsgi_daemon.sh
RemainAfterExit=true
ExecStop = /root/scripts/stop_uwsgi_daemon.sh

[Install]
WantedBy = multi-user.target
EOF

# Create uWSGI start/stop scripts
mkdir /root/scripts
cat > /root/scripts/start_uwsgi_daemon.sh <<EOF
#!/bin/bash
# Start uWSGI as a daemon; installed as service
/usr/local/bin/uwsgi \
  --emperor /etc/uwsgi/vassals \
  --uid rvdas --gid rvdas \
  --pidfile /etc/uwsgi/process.pid \
  --daemonize /var/log/uwsgi-emperor.log
EOF

cat > /root/scripts/stop_uwsgi_daemon.sh <<EOF
#!/bin/bash
/usr/local/bin/uwsgi --stop /etc/uwsgi/process.pid
EOF

chmod 755 /root/scripts/start_uwsgi_daemon.sh /root/scripts/stop_uwsgi_daemon.sh


# Set up nginx
echo "############################################################################"
echo Setting up NGINX
mkdir /etc/nginx/sites-available
mkdir /etc/nginx/sites-enabled

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
  mv /tmp/nginx.conf /etc/nginx/nginx.conf
  echo Done setting up NGINX
fi

# Set up openrvdas
echo "#########################################################################"
echo Fetching and setting up OpenRVDAS code...
cd $INSTALL_ROOT
git clone -b $OPENRVDAS_BRANCH $OPENRVDAS_REPO

echo Initializing OpenRVDAS database...
cd openrvdas
cp django_gui/settings.py.dist django_gui/settings.py
cp database/settings.py.dist database/settings.py

python3 manage.py makemigrations django_gui
python3 manage.py migrate
echo yes | python3 manage.py collectstatic

# Bass-ackwards way of creating superuser $RVDAS_USER, as the createsuperuser
# command won't work from a script
echo "from django.contrib.auth.models import User; User.objects.filter(email='${RVDAS_USER}@example.com').delete(); User.objects.create_superuser('${RVDAS_USER}', '${RVDAS_USER}@example.com', '${RVDAS_PASSWORD}')" | python3 manage.py shell

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
home            = /usr/local

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
mkdir -p /etc/uwsgi/vassals
ln -sf ${INSTALL_ROOT}/openrvdas/django_gui/openrvdas_uwsgi.ini \
      /etc/uwsgi/vassals/

# Make everything accessible to nginx
chmod 755 ${INSTALL_ROOT}/openrvdas
chown -R rvdas ${INSTALL_ROOT}/openrvdas
chgrp -R rvdas ${INSTALL_ROOT}/openrvdas

# Set permissions
echo "############################################################################"
echo Setting SELINUX permissions \(permissive\) and firewall ports
sed -i -e 's/SELINUX=enforcing/SELINUX=permissive/g' /etc/selinux/config

#iptables -A INPUT -p tcp --dport 80 -j ACCEPT
#iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
#iptables -A INPUT -p tcp --dport 8001 -j ACCEPT
#
## Websocket port
#iptables -A INPUT -p tcp --dport 8765 -j ACCEPT
#
## Our favorite UDP port for network data
#iptables -A INPUT -p udp --dport 6224 -j ACCEPT
#
## For unittest access
#iptables -A INPUT -p udp --dport 8000 -j ACCEPT
#iptables -A INPUT -p udp --dport 8001 -j ACCEPT
#iptables -A INPUT -p udp --dport 8002 -j ACCEPT
#
## /etc/init.d/networking restart
#

# Make uWSGI run on boot
systemctl enable uwsgi.service
service uwsgi start

# Make nginx run on boot:
systemctl enable nginx.service
service nginx start


## Commented out stuff about setting OpenRVDAS logger_manager.py
## running as a server.
#
#echo "#########################################################################"
#echo Installing OpenRVDAS server as a service
#cat > /etc/systemd/system/openrvdas.service <<EOF
#[Unit]
#Description = Run openrvdas/server/logger_manager.py as service
#After = network.target
#
#[Service]
#ExecStart = /root/scripts/start_openrvdas.sh
#ExecStop = /root/scripts/stop_openrvdas.sh
#
#[Install]
#WantedBy = multi-user.target
#EOF
#
#cat > /root/scripts/start_openrvdas.sh <<EOF
##!/bin/bash
## Start openrvdas servers as service
#OPENRVDAS_LOGFILE=/var/log/openrvdas.log
#touch \$OPENRVDAS_LOGFILE
#chown $RVDAS_USER \$OPENRVDAS_LOGFILE
#chgrp $RVDAS_USER \$OPENRVDAS_LOGFILE
#sudo -u $RVDAS_USER sh -c "cd $INSTALL_ROOT/openrvdas;/usr/local/bin/python3 server/logger_manager.py --websocket :8765 --database django --no-console -v &>> \$OPENRVDAS_LOGFILE"
#EOF
#
#cat > /root/scripts/stop_openrvdas.sh <<EOF
##!/bin/bash
#USER=rvdas
#sudo -u $USER sh -c 'pkill -f "/usr/local/bin/python3 server/logger_manager.py"'
#EOF
#
#chmod 755 /root/scripts/start_openrvdas.sh /root/scripts/stop_openrvdas.sh
#
#echo "############################################################################"
#echo The OpenRVDAS server can be configured to start on boot. Otherwise you will
#echo need to either run it manually from a terminal \('server/logger_manager.py' from the
#echo openrvdas base directory\) or start as a service \('service openrvdas start'\).
#echo
#while true; do
#    read -p "Do you wish to start the OpenRVDAS server on boot? " yn
#    case $yn in
#        [Yy]* ) systemctl enable openrvdas.service; break;;
#        [Nn]* ) break;;
#        * ) echo "Please answer yes or no.";;
#    esac
#done

echo "#########################################################################"
echo "#########################################################################"
echo Installation complete.
echo 
echo To run server, go to install directory and run logger_manager.py
echo 
echo   cd $INSTALL_ROOT/openrvdas
echo   python3 server/logger_manager.py --websocket :8765 \\
echo                 --database django --no-console -v
echo 
echo "#########################################################################"
echo Finished installation and configuration. You must reboot before some
echo changes take effect.
while true; do
    read -p "Do you wish to reboot now? " yn
    case $yn in
        [Yy]* ) reboot now; break;;
        [Nn]* ) exit;;
        * ) echo "Please answer yes or no.";;
    esac
done

