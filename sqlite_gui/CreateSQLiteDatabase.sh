#!/bin/bash

rm -f openrvdas.sql

# There are only 3 tables:
#   Cruise (hold the cruise definition object)
#   lastupdate (timestamp of last write)
#   logmessages (log messages)

sqlite3 openrvdas.sql 'CREATE TABLE Cruise (highlander integer primary key not null, config blob, [loaded_time] datetime, compressed integer);'
sqlite3 openrvdas.sql 'CREATE TABLE lastupdate (highlander integer primary key not null, [timestamp] datetime);'
sqlite3 openrvdas.sql 'CREATE TABLE logmessages (timestamp datetime primary key not null, loglevel integer, cruise text, source text, user text, message text);'

# We need a time or we think the databse is not initialized
sqlite3 openrvdas.sql 'INSERT INTO lastupdate (highlander, timestamp) VALUES (1, CURRENT_TIMESTAMP);'

# If database compression is turned on (the default), 
# we can get a YAML representation of our current state using:
# sqlite3 openrvdas.sql "SELECT writefile('/dev/stdout', config) from CRUISE" | gzip -dc
