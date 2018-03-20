#!/usr/bin/env bash

# Set up appropriate user and test databases and users for mysql_connector.

if [ ! $# == 2 ]; then
    echo Usage:
    echo
    echo     $0 MYSQL_USER_NAME MYSQL_USER_PASSWORD
    echo
    echo Will create required tables and named MySQL user and give user
    echo access to the newly-created tables.
    exit
fi

if [ ! `which mysql` ]; then
    echo '####################################################################'
    echo NOTE: Before running this script, please install and set up
    echo the appropriate MySQL server.
    echo '####################################################################'
    exit
fi

USER=$1
PWD=$2

# Create databases if they don't exist, and give user access. Also
# give user 'test' access to test database.
#mysql -u root -p$ROOT_PWD <<EOF 
echo Enter MySQL root password
mysql -u root -p <<EOF 

drop user if exists 'test'@'localhost'; 
create user 'test'@'localhost' identified by 'test';

drop user if exists 'rvdas'@'localhost';
create user '$USER'@'localhost' identified by '$PWD';

create database if not exists data character set utf8;
GRANT ALL PRIVILEGES ON data.* TO '$USER'@'localhost';

create database if not exists test character set utf8;
GRANT ALL PRIVILEGES ON test.* TO '$USER'@'localhost';
GRANT ALL PRIVILEGES ON test.* TO 'test'@'localhost' identified by 'test';

flush privileges;
\q

EOF

