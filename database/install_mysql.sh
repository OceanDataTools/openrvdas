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
# Defaults written by/to be read by install_mysql.sh
DEFAULT_INSTALL_ROOT=$INSTALL_ROOT
DEFAULT_RVDAS_USER=$RVDAS_USER
EOF
}

###########################################################################
###########################################################################
function install_mysql_macos {
    echo "#####################################################################"
    echo "Installing and enabling MySQL..."
    HOMEBREW_BASE='/usr/local/homebrew'
    # Put brew in path for now
    eval "$(${HOMEBREW_BASE}/bin/brew shellenv)"

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
# Set up Python packages
function setup_python_packages {
    # Expect the following shell variables to be appropriately set:
    # INSTALL_ROOT - path where openrvdas/ is

    # Set up virtual environment
    VENV_PATH=$INSTALL_ROOT/openrvdas/venv
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

setup_python_packages

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
