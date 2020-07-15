#!/usr/bin/env bash

# Set up appropriate user and test databases and users for pstgresql_connector.

if [ ! $# == 2 ]; then
    echo Usage:
    echo
    echo     $0 POSTGRES_USER_NAME POSTGRES_USER_PASSWORD
    echo
    echo Will create required tables and named PostgreSQL user and give user
    echo access to the newly-created tables.
    exit
fi

if [ ! `which psql` ]; then
    echo '####################################################################'
    echo NOTE: Before running this script, please install and set up
    echo the appropriate PostgreSQL server.
    echo '####################################################################'
    exit
fi

DB_USER=$1
DB_USER_PWD=$2

# Create databases if they don't exist, and give user access. Also
# give user 'test' access to test database.

psql <<EOF 

DROP OWNED BY test;
DROP USER IF EXISTS test;
CREATE USER test WITH PASSWORD 'test';

DROP OWNED BY $DB_USER;
DROP USER IF EXISTS $DB_USER;
CREATE USER $DB_USER WITH PASSWORD '$DB_USER_PWD';

SELECT 'CREATE DATABASE data WITH ENCODING UTF8'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'data')\gexec

GRANT ALL PRIVILEGES ON DATABASE data TO $DB_USER;

SELECT 'CREATE DATABASE test WITH ENCODING UTF8'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'test')\gexec

GRANT ALL PRIVILEGES ON DATABASE test TO test;
GRANT ALL PRIVILEGES ON DATABASE test TO $DB_USER;

\q

EOF