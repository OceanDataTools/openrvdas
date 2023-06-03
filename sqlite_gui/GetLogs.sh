#!/bin/bash

# @/GetLogs.sh ${CRUISE}

# Selects log messages from current (and backup) sqlite databases
# for cruise specified on command line

Q="SELECT cruise FROM logmessages;"
ROOT="/opt/openrvdas/sqlite_gui"
FILE="${ROOT}/openrvdas.sql"

if [ -z ${1} ] ; then
    echo "GetLogs.sh <cruise>"
    AVAIL=`sqlite3 ${FILE} "${Q}" | sort -u`
    echo "    Available cruises:"
    for cruise in ${AVAIL} ; do
    echo "        ${cruise}"
    done
    exit
fi

CRUISE=$1
set -f
Q="SELECT * FROM logmessages WHERE cruise='${CRUISE}';"


sqlite3 ${FILE} "${Q}" |\
while IFS='|' read -r DTG loglevel cruise source user message ; do
    echo "${DTG} ${message}"
done

backupdb=`find ${ROOT} -name "openrvdas-${CRUISE}-*.sql"`
if [ -n "${backupdb}" ] ; then
    for FILE in ${backupdb} ; do
        sqlite3 ${FILE} "${Q}" |\
        while IFS='|' read -r DTG l c s u message ; do
            echo "${DTG} ${message}"
        done
    done
fi

exit
