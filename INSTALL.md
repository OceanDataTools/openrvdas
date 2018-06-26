# OpenRVDAS
At the time of this writing OpenRVDAS was built and tested against MacOS X, CentOS 7 and the Ubuntu 16.04.3 LTS operating system. It may be possible to build against other linux-based operating systems, and guides will be added here as they are verified and documented.

*Note that OpenRVDAS is still very much under development and subject to unannounced changes.*

## CentOS 7 Installation Guide
This document describes building/testing OpenRVDAS on CentOS 7. The code has also been built and tested to varying degrees on Ubuntu, MacOS X and Raspbian (though MacOS and Raspbian install documentation does not yet exist)

### Operating System
Goto <https://www.centos.org/download/>

Download CentOS 7 for your hardware.  At the time of this writing we
are using CentOS-7-x86_64-DVD-1611.iso

NOTE: an experimental script in ```utils/build_openrvdas_centos7.sh``` is designed to perform a full
installation of OpenRVDAS when run on a clean CentOS 7 system. You can download the script from GitHub and run it
as root, and it will install and set up the core logging, database and GUI services (NGINX web server and uWSGI),
requiring only that the user run ```gui/run_servers.py``` to have full system functionality. But the script *is*
still experimental and may break in inexplicable ways.

As an alternative you can manually install OpenRVDAS as follows:

Perform the default CentOS install. Once the installation has completed, open a terminal window and update the installed packages via
```
sudo yum -y install deltarpm
sudo yum -y update
```

Several packages are needed to simplify the installation of OpenRVDAS:
```
sudo yum install -y wget gcc readline-devel zlib-devel openssl-devel 

# If you will be installing the Django GUI:
sudo yum install -y sqlite-devel

```

### Prerequisites
#### Python3
CentOS 7 comes with Python 2.7 by default; the code has only been verified to run on Python 3.5+. To install the current version of Python (at this writing 3.6.3), you will need to download and build it:

```
cd /tmp
wget https://www.python.org/ftp/python/3.6.3/Python-3.6.3.tgz

tar xzf Python-3.6.3.tgz
cd Python-3.6.3

./configure --enable-optimizations --enable-threading --enable-loadable-sqlite-extensions
sudo make
sudo make install
```
Note that the "--enable-optimizations" flag is optional; it will (greatly) increase the time it takes to build Python, but will result in a faster executable.


#### Pyserial
Serial port functionality will require the pyserial.py package, which
may be installed using pip3.  Open a terminal window:

```
  sudo pip3 install pyserial
```

#### Socat
To test the system using the simulate_serial.py utility, you will also need the 'socat' command installed on your system.  To install socat, type the following in a terminal window:
```
sudo yum install -y socat
```

#### Git
Git is used to download the OpenRVDAS source code repository.  Install Git by typing the following in a terminal window:
```
sudo yum install -y git
```
## Ubuntu Installation Guide
### Operating System
Goto <https://www.ubuntu.com/download/desktop>

Download Ubuntu for your hardware.  At the time of this writing we are using 16.04.3 (64-bit)

Perform the default Ubuntu install.  For these instructions the default account that is created is "Survey" and the computer name is "Datalog".

A few minutes after the install completes and the computer restarts, Ubuntu will ask to install any updates that have arrived since the install image was created.  Perform these now and do not continue with these instructions until the update has completed.

Before OpenRVDAS can be installed serveral other software packaged that must be installed and configured.

*Note that OpenRVDAS is still very much under development. The core logging functionality only relies on Python 3 (tested on Python 3.5 and above). You should be able to simply unpack the distribution and run*

### Prerequisites
#### Python3
Open a terminal window and run the following command:
```
sudo apt-get install python3 python3-pip
```

#### Pyserial
Serial port functionality will require the pyserial.py package, which may be installed using pip3.  Open a terminal window:

```
  pip3 install pyserial
```

#### Socat
To test the system using the simulate_serial.py utility, you will also need the 'socat' command installed on your system.  To install socat, type the following in a terminal window:
```
sudo apt-get install socat
```

#### Git
Git is used to download the OpenRVDAS source code repository.  Install Git by typing the following in a terminal window:
```
sudo apt-get install git
```

## Install OpenRVDAS
Once you have installed the above prerequisites, download the source code repository from GitHub.

```
cd ~
git clone https://github.com/davidpablocohn/openrvdas.git
```

## Post-install Testing
Full unit tests for the code base may be run from the project home directory by running:
```
cd ~/openrvdas
python3 -m unittest discover
```

Note that NetworkReader and NetworkWriter tests may fail unless the user has permissions to write UDP to port 8000, 8001 and 8002 on the host machine. Websocket services, by default, will also need TCP access to port 8765. Under CentOS, you can add these permissions with
```
sudo firewall-cmd --permanent --add-port=8000/udp
sudo firewall-cmd --permanent --add-port=8001/udp
sudo firewall-cmd --permanent --add-port=8002/udp
sudo firewall-cmd --permanent --add-port=8765/tcp
sudo firewall-cmd --reload
```

Tests may be run on a directory by directory basis.  For example, to test all code in logger/readers:
```
python3 -m unittest discover logger.readers
```

Specific unit tests may be run individually, as well.  Many (but not yet all) accept -v flags to increase the verbosity of the test: a single '-v' sets logging level to "info"; a second -v sets
it to "debug".
```
logger/readers/test_network_reader.py -v -v
```
## Database and GUI Functionality
To use the database functionality implemented by DatabaseWriter and DatabaseReader, you will also need to follow the installation and configuration instructions in the [database/README.md](database/README.md) file. To use the Django-based GUI, you will need to follow the instructions in [django_gui/README.md](django_gui/README.md).

