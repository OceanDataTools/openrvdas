# OpenRVDAS Installation Guide
At the time of this writing OpenRVDAS has been built and tested against MacOS X, CentOS 7 and  Ubuntu 18 operating systems. It may be possible to build against other Linux-based operating systems, and guides will be added here as they are verified and documented.

*Note that OpenRVDAS is still very much under development and subject to unannounced changes.*

## Scripted Installation

_This is the recommended way to install for CentOS 7 and Ubuntu 18._

Grab the script (centos7 or ubuntu18, as appropriate for your distribution):

```
# Get build script from Github
wget \
  https://raw.githubusercontent.com/davidpablocohn/openrvdas/master/utils/build_openrvdas_centos7.sh
```

Now run the script as sudo

```
chmod 755 ./build_openrvdas_centos7.sh
sudo ./build_openrvdas_centos7.sh
```

_The script will ask a lot of questions and provide default answers in parens that will be filled in if you hit "return"; without any other input:_

############################################################################

```
OpenRVDAS configuration script
Do you wish to continue? **y**
Name to assign to host (lmg-dast-s1-t)?
Hostname will be 'lmg-dast-s1-t'
Install root? (/opt)
Install root will be '/opt'
```

_Script will next ask which code repo and branch to use. Use the default repo and branch unless you have a project-specific branch in mind (e.g. "usap"). If you need to access the internet via a proxy (as shown below), enter it when asked; otherwise just hit return._

```
Repository to install from? (http://github.com/davidpablocohn/openrvdas)
Repository branch to install? (master)
HTTP/HTTPS proxy to use (http://proxy.lmg.usap.gov:3128)?
Setting up proxy http://proxy.lmg.usap.gov:3128
Will install from github.com
Repository: 'http://github.com/davidpablocohn/openrvdas'
Branch: 'master'
```

_Script will try to create the rvdas user under which the system will run. It won't mind if the user already exists:_

```
OpenRVDAS user to create? (rvdas)
Checking if user rvdas exists yet
User exists, skipping
```

_Script will next ask about database options. If this is the first time you've run the script and MySQL/MariaDB has not already been installed, the current root database password will be empty:_

```
Database password to use for rvdas? (rvdas)
Current database password for root? (if one exists - hit return if not)
New database password for root? () **rvdas**

############################################################################
The OpenRVDAS server can be configured to start on boot. Otherwise
you will need to either run it manually from a terminal (by running
server/logger_manager.py from the openrvdas base directory) or
start as a service (service openrvdas start).

Do you wish to start the OpenRVDAS server on boot? **y**
```

The script will run a while and ask at the end if you want to reboot. If you need to do the post-installation step(s) below, say "no", perform those steps, then reboot. Otherwise, say yes, then log in afterwards and check ``/var/log/openrvdas/openrvdas.log`` to make sure things have come up properly.

## Post-Installation

The installation should allow you to connect via http to the server at the name you specified at the start of the script (e.g. ``lmg-dast-s1-t``). If you want to connect using any other names, e.g. the fully-qualified domain name ``lmg-dast-s1-t.lmg.usap.gov``, you'll need to add it to the Django server settings file in ``django_gui/settings.py``:

```
ALLOWED_HOSTS = [HOSTNAME, 'localhost', HOSTNAME + '.lmg.usap.gov']
```
If you didn't reboot immediately after installation, reboot now.

If you answered 'no' to whether OpenRVDAS should start automatically on boot up, you can manually start/stop the service via:
```service openrvdas start```
and
```service openrvdas stop```

## Manual Installation

As a (somewhat painful) alternative, you can manually install OpenRVDAS.

### Create RVDAS user
First set up our default OpenRVDAS user:

```
  adduser rvdas
  passwd rvdas   # set the password to what you want
  usermod -a -G tty rvdas # allow user access to serial ports
```

### Install required packages
The standard OpenRVDAS installation requires extra packages. 

#### On CentOS7, run:
```
sudo yum -y install deltarpm epel-release
sudo yum -y update
sudo yum install -y socat git nginx sqlite-devel readline-devel \
    wget gcc zlib-devel openssl-devel \
    python36 python36-devel python36-pip
```
If you have firewalld installed and running, you'll need to open some ports for UDP and TCP:
```
firewall-cmd --permanent --add-port=80/tcp > /dev/null
firewall-cmd --permanent --add-port=8000/tcp > /dev/null
firewall-cmd --permanent --add-port=8001/tcp > /dev/null

# Websocket ports
firewall-cmd --permanent --add-port=8765/tcp > /dev/null # status
firewall-cmd --permanent --add-port=8766/tcp > /dev/null # data

# Our favorite UDP port for network data
firewall-cmd --permanent --add-port=6224/udp > /dev/null
firewall-cmd --permanent --add-port=6225/udp > /dev/null

# For unittest access
firewall-cmd --permanent --add-port=8000/udp > /dev/null
firewall-cmd --permanent --add-port=8001/udp > /dev/null
firewall-cmd --permanent --add-port=8002/udp > /dev/null
firewall-cmd --reload > /dev/null
```

#### On Ubuntu 18, run:
```    
sudo apt-get update
sudo apt install -y socat git nginx python3-dev python3-pip libreadline-dev \
    mysql-common mysql-client libmysqlclient-dev libsqlite3-dev 
sudo apt install -y openssh-server
sudo systemctl restart ssh
```

### Install default database

#### CentOS 7
For now, the default CentOS 7 database used by OpenRVDAS is MariaDB, an open source equivalent of MySQL:
```
sudo yum install -y mariadb-server mariadb-devel mariadb-libs
sudo service mariadb restart              # to manually start db server
sudo systemctl enable mariadb.service     # to make it start on boot
sudo /usr/bin/mysql_secure_installation
```

#### Ubuntu 18
```
sudo apt install -y mysql-server
sudo mysql_secure_installation
update-rc.d mysql defaults
```

### Set some security options
SELinux can cause some mysterious failures. The default script tweaks are:
```
setsebool -P nis_enabled 1
setsebool -P use_nfs_home_dirs 1
setsebool -P httpd_can_network_connect 1
semanage permissive -a httpd_t
```

### Configure the database
Create a database user corresponding to your OpenRVDAS user. Run
```
mysql -u root -p
```

Then, in the program, run the following commands:
```
create user test@localhost identified by 'test';
create user rvdas@localhost identified by 'pick_an_rvdas_database_password_here';

create database data character set utf8;
GRANT ALL PRIVILEGES ON data.* TO rvdas@localhost;

create database openrvdas character set utf8;
GRANT ALL PRIVILEGES ON openrvdas.* TO rvdas@localhost;

create database test character set utf8;
GRANT ALL PRIVILEGES ON test.* TO rvdas@localhost;
GRANT ALL PRIVILEGES ON test.* TO test@localhost identified by 'test';
flush privileges;
\q
```

### Install required Python packages
OpenRVDAS requires some additional Python packages as well. Install them with pip3:

```
  sudo pip3 install --upgrade pip
  sudo pip3 install Django==2.0 pyserial uwsgi websockets PyYAML \
       parse mysqlclient mysql-connector
```

### Install OpenRVDAS code

Go to the directory where you want the system installed (/opt in this example) and clone the code using Git:
```
cd /opt
git clone  http://github.com/davidpablocohn/openrvdas
```

Copy over and modify a few of the config files so that they reflect our choice of OpenRVDAS user and password:
```
HOSTNAME=your_hostname_here
RVDAS_USER=rvdas
RVDAS_DATABASE_PASSWORD=same_password_as_you_used_above_for_database

cd openrvdas
cp django_gui/settings.py.dist django_gui/settings.py
sed -i -e "s/'USER': 'rvdas'/'USER': '${RVDAS_USER}'/g" django_gui/settings.py
sed -i -e "s/'PASSWORD': 'rvdas'/'PASSWORD': '${RVDAS_DATABASE_PASSWORD}'/g" django_gui/settings.py

cp database/settings.py.dist database/settings.py
sed -i -e "s/DEFAULT_DATABASE_USER = 'rvdas'/DEFAULT_DATABASE_USER = '${RVDAS_USER}'/g" database/settings.py
sed -i -e "s/DEFAULT_DATABASE_PASSWORD = 'rvdas'/DEFAULT_DATABASE_PASSWORD = '${RVDAS_DATABASE_PASSWORD}'/g" database/settings.py

cp widgets/static/js/widgets/settings.js.dist \
   widgets/static/js/widgets/settings.js
sed -i -e "s/localhost/${HOSTNAME}/g" widgets/static/js/widgets/settings.js
```

Initialize the Django database
```
python3 manage.py makemigrations django_gui
python3 manage.py migrate
echo yes | python3 manage.py collectstatic
```

### Test basic operation

In one terminal, start a simulated serial port feed as user **rvdas**:
```
su rvdas
cd /opt/openrvdas
logger/utils/simulate_serial.py --config test/NBP1406/serial_sim_NBP1406.yaml --loop
```
In another terminal, try reading from one of the simulated serial ports as user **rvdas**:
```
cd /opt/openrvdas
logger/listener/listen.py --serial port=/tmp/tty_s330 \
  --transform_timestamp \
  --transform_prefix s330 \
  --write_file -
```
Try reading from the simulated serial port and writing to the database:
```
logger/listener/listen.py --serial port=/tmp/tty_s330 \
  --transform_timestamp \
  --transform_prefix s330 \
  --transform_parse --write_file - \
  --database_password <your database password> \
  --write_database rvdas@localhost:data
```
Go to the database in another terminal to verify data are being written:
```
mysql -u rvdas -p
> use data;
> select * from data;
```
Try writing to the network and reading the written records in another terminal:
```
cd /opt/openrvdas
logger/listener/listen.py --serial port=/tmp/tty_s330 \
  --transform_timestamp \
  --transform_prefix s330 \
  --write_file - \
  --write_network :6224
```
In the other terminal:
```
logger/listener/listen.py --network :6224 \
  --write_file -
```

### GUI Functionality
To use the Django-based GUI, you will need to follow the instructions in [django_gui/README.md](django_gui/README.md).
