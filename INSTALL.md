
# OpenRVDAS

## Installation Guide
At the time of this writing OpenRVDAS was built and tested against the Ubuntu 16.04.3 LTS operating system. It may be possible to build against other linux-based operating systems however for the purposes of this guide the instructions will assume Ubuntu 16.04.3 LTS is used.

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
Serial port functionality will require the pyserial.py package, which
may be installed using pip3.  Open a terminal window :

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

### Install OpenRVDAS

Download the source code repository from GitHub.

```
cd ~
git clone https://github.com/davidpablocohn/openrvdas.git
```

### Post-install Testing

***NOTE: These test currently fail when using these installation instructions.  This is being addressed***

Full unit tests for the code base may be run from the project home
directory by running:
```
cd ~/openrvdas
python3 -m unittest discover
```

Tests may be run on a directory by directory basis.  For example, to test all code in logger/readers:
```
python3 -m unittest discover logger.readers
```

Specific unit tests may be run individually, as well.  Many (but not yet all) accept -v flags to increase the verbosity of
the test: a single '-v' sets logging level to "info"; a second -v sets
it to "debug".
```
    logger/readers/test_network_reader.py -v -v
```
