# OpenRVDAS
At the time of this writing OpenRVDAS was built and tested against MacOS X, CentOS 7 and the Ubuntu 16.04.3 LTS operating system. It may be possible to build against other linux-based operating systems, and guides will be added here as they are verified and documented.

*Note that OpenRVDAS is still very much under development and subject to unannounced changes.*

### Scripted Installation

_This is the recommended way to install for CentOS 7, Ubuntu 16 and Ubuntu 18._

Copy the script ``utils/build_openrvdas_centos7.sh`` (or respectively ``utils/build_openrvdas_ubuntu16.sh``
or ``utils/build_openrvdas_ubuntu18.sh``) into the /tmp
directory of your new machine. When run as root, it will install and
set up the core logging, database and GUI services (NGINX web server
and uWSGI). The script also provides the option of configuring the
OpenRVDAS servers to start automatically on boot or manually, via

```service openrvdas start```

and shut down via

```service openrvdas stop```

### Manual Installation

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

On CentOS7, run:
```
sudo yum -y install deltarpm epel-release
sudo yum -y update
sudo yum install -y socat git nginx sqlite-devel readline-devel \
    wget gcc zlib-devel openssl-devel \
    python36 python36-devel python36-pip
```

On Ubuntu 18, run:
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
logger/listener/listen.py --serial po=/tmp/tty_s330 \
  --transform_timestamp \
  --transform_prefix s330 \
  ---transform_parse --write_file - \
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

## GUI Functionality
To use the Django-based GUI, you will need to follow the instructions in [django_gui/README.md](django_gui/README.md).

