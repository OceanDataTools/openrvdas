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
HOST_PATH=http://157.245.173.52:8000/api/
CRUISE_FILE=${SCRIPT_DIR}/cruise.yaml
CONFIG_TEMPLATE=${SCRIPT_DIR}/config_template.yaml
echo
echo Setting script to read CORIOLIX variables from $HOST_PATH
echo Setting script to write cruise definitions to $CRUISE_FILE
read -p "Hit any key to continue, or Ctl-C to exit "
echo

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

# Do we already have a program for build_cruise_definition?
if grep -q build_cruise_definition $SUP_FILE; then
    echo Supervisor file already has script added
    return -1 2> /dev/null || exit -1  # exit correctly if sourced/bashed
fi

# If we're here, it's time to add the new definitions to supervisor file
echo Adding build_cruise_definition to supervisor file $SUP_FILE

cp $SUP_FILE /tmp/temp_sup_file
cat >> /tmp/temp_sup_file <<EOF

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
sudo cp /tmp/temp_sup_file $SUP_FILE

echo Success!
