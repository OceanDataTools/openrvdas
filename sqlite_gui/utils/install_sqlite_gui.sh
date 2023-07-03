#!/bin/bash

# Warning:  Bashism's ahead.
########################################
#
# Initial default values
#
########################################
RANDOM_SECRET=0
MAKE_CERT=0
USE_HTTP=0

########################################
#
# If a preferences file exists, use it
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
    echo " -OS_TYPE <type>  Override automatic detection of OS_TYPE and use the"
    echo "             supplied option.  Currently will accept:"
    echo "             Ubuntu - use for debian derived distros"
    echo "             CentOS - use for redhat derived distros"
    echo "             Darwin - use for apple products"
    echo " -secret <\"quoted text\">   Secret for CGI's to use for auth"
    echo " -randomsecret  Generate a random secret"
    echo " -http       Use (non-secure) http instead of https"
    echo
    echo "On exiting the script, preferences will be written out"
}

# On exit, create prefs file
function on_exit {
    echo "Writing preferences file"
    rm -f .sqlitegui.prefs
    # Redirect all further output onto the prefs file
    exec > .sqlitegui.prefs
    echo "OS_TYPE=${OS_TYPE}"
    echo "MAKE_CERT=${MAKE_CERT}"
    echo "BASEDIR=${BASEDIR}"
    echo "USE_HTTP=${USE_HTTP}"
    echo "RANDOM_SECRET=${RANDOM_SECRET}"
    # For security purposes, do not save SECRET in prefs file ??
    # [[ -n "${SECRET}" ]] && echo "SECRET=\"${SECRET}\""
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
             MAKE_CERT=0
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
         -randomsecret)
             RANDOM_SECRET=1
             ;;
         -secret)
             SECRET=$2
             shift
             ;;
         -http)
             USE_HTTP=1
             ;;
         -h)
             show_help
             exit
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
    # running OpenRVDAS.  Simplified.  Just get the flavor.
    if [ `uname -s` == 'Darwin' ] ; then
        OS_TYPE=MacOS
        return
    fi
    LIKE=`grep -i "id_like" /etc/os-release`
    # This will work on Fedora, Rocky, RHEL, CentOS, etc.
    [[ ${LIKE} =~ 'rhel' ]] && OS_TYPE='CentOS'
    # This will work on debian, ubuntu, RaspiOS, etc...
    [[ ${LIKE} =~ 'debian' ]] && OS_TYPE='Ubuntu'
    # SUSE/OpenSUSE say "suse" in the id_like
}

### Supervisor
function setup_supervisor {
    echo "Setting up the supervisor config for SQLite GUI"
    if [ $OS_TYPE == 'MacOS' ]; then
        SUPERVISOR_DIR=/usr/local/etc/supervisor.d/
        SUPERVISOR_FILE=$SUPERVISOR_DIR/openrvdas_sqlite.ini

    # CentOS/RHEL
    elif [ $OS_TYPE == 'CentOS' ]; then
        SUPERVISOR_DIR=/etc/supervisord.d
        SUPERVISOR_FILE=$SUPERVISOR_DIR/openrvdas_sqlite.ini

    # Ubuntu/Debian
    elif [ $OS_TYPE == 'Ubuntu' ]; then
        SUPERVISOR_DIR=/etc/supervisor/conf.d
        SUPERVISOR_FILE=$SUPERVISOR_DIR/openrvdas_sqlite.conf
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
    [[ -f ../sqlite_server_api.py ]] && BASEDIR=`normalize_path "${PWD}/.."`
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
    cd ../nginx
    if [ -f openrvdas.crt -a -f openrvdas.key ] ; then
        echo "Looks like you already have required certificates."
        echo "If you want to over-write them, cd to ../nginx"
        echo "and run GenerateCert.sh"
    else
        /bin/bash GenerateCert.sh
    fi
    cd ${SAVEPWD}
}

function overwrite_logger_manager {
    # FIXME"  This needs to be obsoleted.
    # Save the original logger_manager
    SERVERDIR=${BASEDIR}/server
    SQLITESRV=${BASEDIR}/sqlite_gui/server
    # /bin/cp ${SQLITESRV}/logger_manager.py ${SERVERDIR}/
}

function random_secret {
    echo "Generating a random secret for CGI's"
    x=""
    count=`echo ${RANDOM} | cut -b1-2`
    for i in `seq 1 ${count}` ; do 
        x=${RANDOM}${x}${RANDOM}
    done
    SECRET=`echo ${x} | md5sum - | cut -b1-32`
    echo ${SECRET}
}

function set_secret {
    # sed the secret into secret.py
    echo "Setting the secret used for CGI's"
    SAVEPWD=${PWD}
    CGIDIR=../cgi-bin
    cd ${CGIDIR}
    /usr/bin/sed -ie "s/_SECRET = \".*\"/_SECRET = \"${SECRET}\""/ secret.py
    /bin/rm =f secret.pye
    unset SECRET
    cd ${SAVEPWD}
}

function downgrade_nginx {
    echo "Setting nginx to use (non-secure) port 80"
    SAVEPWD=${SAVEPWD}
    NGINXDIR=${BASEDIR}/sqlite_gui/nginx
    SED="/usr/bin/sed -ie"
    cd ${NGINXDIR}
    # sure, http2 is cool, but sed the sadness.
    ${SED} 's/listen.*9000.*/listen \*:9000;/' nginx_sqlite.conf
    ${SED} 's/listen.*443.*/listen \*:80;/' nginx_sqlite.conf
    rm -f nginx_sqlite.confe
    :
    cd ${SAVEPWD}
}

function add_python_packages {
    packages="PyJWT yamllint  py-setproctitle"
    echo "Installing python libraries: ${packages}"
    for pkg in $packages ; do
        pip -q install $pkg
    done
}

get_basedir
setup_supervisor
# FIXME:  Instead, patch so we run logger_manager from our dir ??
overwrite_logger_manager
# We might have OS_TYPE in prefs
[[ -z "${OS_TYPE}" ]] && determine_flavor
# Generate cert/key for nginx if requested
[[ ${MAKE_CERT} == 1 ]] && make_certificate
# Generate a random secret if requested
[ ${RANDOM_SECRET} == 1 ] && SECRET=`random_secret`
# If we have a secret (supplied or random), set it
[ -n "${SECRET}" ] && set_secret
# Add python packages 
add_python_packages
# ... well... you never know... use http
[[ ${USE_HTTP} == 1 ]] && downgrade_nginx
