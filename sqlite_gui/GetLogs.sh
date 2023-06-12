#!/bin/bash

# @/GetLogs.sh ${CRUISE}

# If we've done things right, all the CGI's (and the api_tool) will
# log to the messagelog any time they make a change in logger or
# cruise mode state.  This allows us to extract a comprehensive
# report of logger state with a simple SQL query.

# Resolves OceanDataTools/openrvdas#279

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

echo "...Searching backup databases"
backupdb=`find ${ROOT} -name "openrvdas-${CRUISE}-*.sql"`
if [ -n "${backupdb}" ] ; then
    for FILE in ${backupdb} ; do
        echo "...backup database: ${FILE}"
        sqlite3 ${FILE} "${Q}" |\
        while IFS='|' read -r DTG l c s u message ; do
            echo "${DTG} ${message}"
        done
    done
fi

exit
