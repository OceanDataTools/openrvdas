#!/bin/bash -e

# This script should only be run after OpenRVDAS has been installed
# using one of the installation scripts in the utils/ directory. When
# run, it will add a new program to the supervisor's openrvdas.ini
# file that will allow calling the build_cruise_definition.py script
# to be triggered via supervisor.
#
# This will also allow (under the default installation), triggering
# the script via a call to supervisord's web interface:
#
#   wget -O - 'http://localhost:9001/index.html?processname=build_cruise_definition&action=start' > /dev/null

SCRIPT_DIR=`dirname $0`
INSTALL_ROOT=`cd $SCRIPT_DIR/../../.. && pwd`
VENV_BIN=${INSTALL_ROOT}/openrvdas/venv/bin

# HOST_PATH and CRUISE_FILE should be set as appropriate for your
# installation
DEFAULT_HOST_PATH='http://127.0.0.1:8000/api/'
DEFAULT_CRUISE_FILE=${SCRIPT_DIR}/cruise.yaml
DEFAULT_CONFIG_TEMPLATE=${SCRIPT_DIR}/config_template.yaml

PREFERENCES_FILE=${SCRIPT_DIR}/.coriolix_preferences

###########################################################################
###########################################################################
# Read any pre-saved default variables from file
function set_default_variables {
    # Defaults that will be overwritten by the preferences file, if it
    # exists.
    DEFAULT_HOST_PATH=$DEFAULT_HOST_PATH
    DEFAULT_CRUISE_FILE=$DEFAULT_CRUISE_FILE
    DEFAULT_CONFIG_TEMPLATE=$DEFAULT_CONFIG_TEMPLATE

    # Read in the preferences file, if it exists, to overwrite the defaults.
    if [ -e $PREFERENCES_FILE ]; then
        echo Reading pre-saved defaults from "$PREFERENCES_FILE"
        source $PREFERENCES_FILE
    fi
}

###########################################################################
###########################################################################
# Save defaults in a preferences file for the next time we run.
function save_default_variables {
    cat > $PREFERENCES_FILE <<EOF
# Defaults written by/to be read by setup.sh
DEFAULT_HOST_PATH=$HOST_PATH
DEFAULT_CRUISE_FILE=$CRUISE_FILE
DEFAULT_CONFIG_TEMPLATE=$CONFIG_TEMPLATE
EOF
}

set_default_variables

echo "#####################################################################"
read -p "CORIOLIX API HOST_PATH ($DEFAULT_HOST_PATH)? " HOST_PATH
HOST_PATH=${HOST_PATH:-$DEFAULT_HOST_PATH}

echo "#####################################################################"
read -p "CORIOLIX cruise definition file template ($DEFAULT_CONFIG_TEMPLATE)? " CONFIG_TEMPLATE
CONFIG_TEMPLATE=${CONFIG_TEMPLATE:-$DEFAULT_CONFIG_TEMPLATE}

echo "#####################################################################"
read -p "OpenRVDAS cruise definition file ($DEFAULT_CRUISE_FILE)? " CRUISE_FILE
CRUISE_FILE=${CRUISE_FILE:-$DEFAULT_CRUISE_FILE}

echo
echo Setting script to read CORIOLIX variables from $HOST_PATH
echo Setting script to use the cruise definition template: $CONFIG_TEMPLATE
echo Setting script to write cruise definitions to $CRUISE_FILE
read -p "Hit any key to continue, or Ctl-C to exit "
echo

save_default_variables

#return -1 2> /dev/null || exit -1  # exit correctly if sourced/bashed

# Copy distribution version of template file over to version that will
# be used.
echo Copying template definition file into place ${CONFIG_TEMPLATE}.dist -\> $CONFIG_TEMPLATE
cp -i ${CONFIG_TEMPLATE}.dist $CONFIG_TEMPLATE

PLATFORM_STRING=`python3 -m platform`
case $PLATFORM_STRING in
    *Darwin* )
        PLATFORM='Darwin'
        ;;
    *macOS* )
        PLATFORM='Darwin'
        ;;
    *Ubuntu* )
        PLATFORM='Ubuntu'
        ;;
    *centos* )
        PLATFORM='CentOS'
        ;;
    * )
        echo Platform not recognized: "$PLATFORM_STRING"
        return -1 2> /dev/null || exit -1  # exit correctly if sourced/bashed
esac

echo Recognized platform $PLATFORM
if [[ $PLATFORM == 'Darwin' ]]; then
    SUP_FILE='/usr/local/etc/supervisor.d/openrvdas.ini'

elif [[ $PLATFORM == 'Ubuntu' ]]; then
    echo Ubuntu
    SUP_FILE='/etc/supervisor/conf.d/openrvdas.conf'
elif [[ $PLATFORM == 'CentOS' ]]; then
    echo CentOS
    SUP_FILE='/etc/supervisord.d/openrvdas.ini'
else
    echo Platform not recognized: "$PLATFORM"
    return -1 2> /dev/null || exit -1  # exit correctly if sourced/bashed
fi

# Does supervisor file exist?
if [[ ! -e $SUP_FILE ]]; then
    echo "No supervisor file found at '$SUP_FILE'; nothing to do"
    return -1 2> /dev/null || exit -1  # exit correctly if sourced/bashed
fi

cp $SUP_FILE /tmp/temp_sup_file

cat > /tmp/build_cruise_definition_supervisor_conf <<EOF
; Script to check CORIOLIX database and update the cruise definition
; file if it has changed.
[program:build_cruise_definition]
command=${VENV_BIN}/python local/rcrv/build_cruise_definition.py  --template local/rcrv/config_template.yaml --host_path $HOST_PATH --destination $CRUISE_FILE
directory=${INSTALL_ROOT}/openrvdas
startsecs=0
autostart=false
autorestart=false
stderr_logfile=/var/log/openrvdas/build_cruise_definition.err.log
stdout_logfile=/var/log/openrvdas/build_cruise_definition.out.log
;user=$RVDAS_USER
EOF

# Do we already have a program for build_cruise_definition?
if grep -q "### BEGIN CORIOLIX GENERATED CONTENT" $SUP_FILE; then
    echo Updating existing build_cruise_definition configuration within Supervisor file $SUP_FILE

    lead='^### BEGIN CORIOLIX GENERATED CONTENT$'
    tail='^### END CORIOLIX GENERATED CONTENT$'
    sed -e "/$lead/,/$tail/{ /$lead/{p;r /tmp/build_cruise_definition_supervisor_conf
        }; /$tail/p;d; }"  /tmp/temp_sup_file > /tmp/updated_sup_file
    sudo cp /tmp/updated_sup_file $SUP_FILE
    # return -1 2> /dev/null || exit -1  # exit correctly if sourced/bashed

else

    # If we're here, it's time to add the new definitions to supervisor file
    echo Adding build_cruise_definition configuration to Supervisor file $SUP_FILE
    echo "### BEGIN CORIOLIX GENERATED CONTENT" >> /tmp/temp_sup_file
    cat /tmp/build_cruise_definition_supervisor_conf >> /tmp/temp_sup_file
    echo "### END CORIOLIX GENERATED CONTENT" >> /tmp/temp_sup_file
    sudo cp /tmp/temp_sup_file $SUP_FILE

fi

echo Success!
