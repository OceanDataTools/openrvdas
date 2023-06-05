#!/bin/bash

rm -f openrvdas.sql

sqlite3 openrvdas.sql 'CREATE TABLE Cruise (highlander integer primary key not null, config blob, [loaded_time] timestamp, compressed integer);'
sqlite3 openrvdas.sql 'CREATE TABLE lastupdate (highlander integer primary key not null, [timestamp] timestamp);'
sqlite3 openrvdas.sql 'INSERT INTO lastupdate (highlander, timestamp) VALUES (1, CURRENT_TIMESTAMP);'
sqlite3 openrvdas.sql 'CREATE TABLE logmessages (timestamp timestamp primary key not null, loglevel integer, cruise text, source text, user text, message text);'
