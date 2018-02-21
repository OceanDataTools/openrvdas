#!/usr/bin/env bash

# Set up appropriate user and test databases and users for mysql_connector.

if [ ! $# == 3 ]; then
    echo Usage: $0 MYSQL_ROOT_PASSWORD MYSQL_USER_NAME MYSQL_USER_PASSWORD
    exit
fi

if [ ! `which mysql` ]; then
    echo '####################################################################'
    echo NOTE: Before running this script, please install and set up
    echo the appropriate MySQL server.
    echo '####################################################################'
    exit
fi

ROOT_PWD=$1
USER=$2
PWD=$3

# Create databases if they don't exist, and give user access. Also
# give user 'test' access to test database.
mysql -u root -p$ROOT_PWD <<EOF 

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

