#!/bin/bash

########################################
#
# If a config file exists, use it
#
########################################
[ -e .sqlitegui.prefs ] && source .sqlitegui.prefs

########################################
#
# Process command line options
#
########################################
function show_help {
    echo "Basic installation script for the sqlite_gui extension to"
    echo "OpenRVDAS."
    echo
    echo "On startup, reads .sqlitegui.prefs.  These preferences can"
    echo "be over-ridden by command line arguments."
    echo
    echo "Arguments:"
    echo " -h          show this help message"
    echo " -f <file>   load alternate config file.  Preferences will be"
    echo "             processed in the order found, so command line args"
    echo "             might get over-ridden by the included config"
    echo " -makecert   Create certificates for nginx (if you don't have any)"
    echo " -nomakecert  Don't create a certificate"
    echo " -OS_TYPE <type>  Bypass automatic detection of OS_TYPE and use the"
    echo "             supplied option.  Currently will accept:"
    echo "             Ubuntu - use for debian derived distros"
    echo "             CentOS - use for redhat derived distros"
    echo "             Darwin - use for apple products"
    echo
    echo "On exiting the script, preferences will be written out"
}

# On exit, create prefs file
function on_exit {
    exec > .sqlitegui.prefs
    [[ -n "${OS_TYPE}" ]] && echo "OS_TYPE=${OS_TYPE}"
    [[ -n "${MAKE_CERT}" ]] && echo "MAKE_CERT=${MAKE_CERT}"
    [[ -n "${BASEDIR}" ]] && echo "BASEDIR=${BASEDIR}"
}
trap on_exit EXIT

while [ $# -gt 0 ] ; do
    case "$1" in
         -f)
             if [ -f $2 ] ; then
                 source $2
             else
                 echo "Config file not found: $2"
             fi
             shift
             ;;
         -makecert)
             MAKE_CERT=1
             ;;
         -nomakecert)
             unset MAKE_CERT
             ;;
         -OS_TYPE)
             OS_TYPE=$2
             shift
             ;;
         -basedir)
             if [ -d $2 ] ; then
                 BASEDIR=$2
             else
                 echo "basedir not a directory: $2"
             fi
             shift
             ;;
         -h)
             show_help
             ;;
         *)
             echo "Ignoring unknown option: $1"
             ;;
    esac
    shift
done

function ask_os_type {
    declare -A allowed
    allowed[CentOS]=CentOS
    allowed[Ubuntu]=Ubuntu
    allowed[Darwin]=Darwin
    echo "Cannot determine the OS Type.  Please select"
    while [ -z ${OS_TYPE} ] ; do
        read -p "(CentOS, Ubuntu, Darwin): " reply
        [ -z "${reply}" ] && reply="Argabarg"   # Blank indexes bad
        [[ ${allowed[$reply]+_} ]] && OS_TYPE=$reply
    done
}

function determine_flavor {
    # We don't need to check versions because they're already
    # running OpenRVDAS.  So just get the flavor.
    if [ `uname -s` == 'Darwin' ] ; then
        OS_TYPE=MacOS
        return
    fi
    LIKE=`grep -i "id_like" /etc/os-release`
    [[ ${LIKE} =~ 'rhel' ]] && OS_TYPE='CentOS'
    [[ ${LIKE} =~ 'debian' ]] && OS_TYPE='Ubuntu'
}

### Supervisor
function setup_supervisor {
    if [ $OS_TYPE == 'MacOS' ]; then
        SUPERVISOR_DIR=/usr/local/etc/supervisor.d/
        SUPERVISOR_FILE=$SUPERVISOR_DIR/openrvdas.ini

    # CentOS/RHEL
    elif [ $OS_TYPE == 'CentOS' ]; then
        SUPERVISOR_DIR=/etc/supervisord.d
        SUPERVISOR_FILE=$SUPERVISOR_DIR/openrvdas.ini

    # Ubuntu/Debian
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        SUPERVISOR_DIR=/etc/supervisor/conf.d
        SUPERVISOR_FILE=$SUPERVISOR_DIR/openrvdas.conf
    fi

    if [ -n "${SUPERVISOR_DIR}" ] ; then
        SOURCE=${BASEDIR}/sqlite_gui/Supervisor/openrvdas_sqlite.ini
        DEST=${SUPERVISOR_FILE}
        if [ -f ${DEST} ] ; then
            echo "Not overwriting existing supervisor config file"
        else
            /bin/cp ${SOURCE} ${DEST}
        fi
    else
        echo "Unable to set up supervisor for you."
    fi
}

function normalize_path {
    echo $(cd ${1} ; echo ${PWD})
}


function get_basedir {
    this_dir=${0%/*}
    [[ $this_dir == $0 ]] && this_dir=${PWD}
    cd $this_dir
    [[ -d ../sqlite_server_api.py ]] && BASEDIR=`normalize_path "${PWD}/.."`
    while [ -z "${BASEDIR}" ] ; do
        echo "Enter the path to the sqlite_gui directory: "
        read reply
        if [ -d ${reply} ] ; then
            BASEDIR=${reply}
        else
            echo "Nope:  try again"
        fi
    done
}

function make_certificate {
    SAVEPWD=${PWD}
    # FIXME:  What if we're not in the right directory to start with?
    cd ../nginx
    if [ -f openrvdas.crt ] ; then
        echo "Looks like you already have certificates."
        echo "If you want to over-write them, cd to ../nginx"
        echo "and run GenerateCert.sh"
    else
        bash GenerateCert.sh
    fi
    cd ${SAVEPWD}
}

function overwrite_logger_manager {
    # Save the original logger_manager
    SERVERDIR=${BASEDIR}/server
    SQLITESRV=${BASEDIR}/sqlite_gui/server
    /bin/cp ${SERVERDIR}/logger_manager.py ${SERVERDIR}/logger_manager.orig
    /bin/cp ${SQLITESRV}/logger_manager.py ${SERVERDIR}/
}

get_basedir
# FIXME:  Instead, patch so we run logger_manager from our dir
overwrite_logger_manager
[[ -z "${OS_TYPE}" ]] && determine_flavor
setup_supervisor
[[ ${MAKE_CERT} == 1 ]] && make_certificate
# I guess make an option for http/https
# The only change necessary is to change the "listen" line to "listen *:80"
# on the / config, and ... we'll have to work it out for Supervisor.

