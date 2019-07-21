# OpenRVDAS Database Operations

## Overview

Please see the [README.md file in the parent directory](../README.md)
for an introduction to the OpenRVDAS system. This document discusses
specifically setting up OpenRVDAS to read/write logger data from/to
a database using DatabaseReader and DatabaseWriter.

Note that Django, [as discussed in the django_gui subdir](../django_gui/README.md),
has its own database setup - what is described below is only relevant
to DatabaseReader and DatabaseWriter.

## Connectors

DatabaseReader and DatabaseWriter are decoupled from the actual
underlying database that will be used, and access via a connector
class defined (by import) in [database/settings.py](settings.py).
The methods that such a connector class should implement are described
below in "Connector Class Methods."

## Installation - MySQL, MariaDB and MongoDB

If you have used one of the installation scripts included in [the top-level utils directory](../utils/)
or followed the instructions in the top-level [INSTALL.md](../INSTALL.md) document, then database
installation is complete for the MySQL/Maria database connector.

If you wish to use MongoDB instead,
you should execute the [setup_mongo_connector.sh](setup_mongo_connector.sh) script in this
directory. If you do the latter and are planning to also use Django, you will need to modify
[django_gui/settings.py](../django_gui/settings.py) to add the appropriate database, user name
and password to its DATABASES declaration.

### Other Connectors

To use another database, you will need to create a new connector
class that implements the methods below, and edit database/settings.py
to import it as "Connector".

## Connector Class methods

A connector class should implement the following methods:
```
  __init__(self, database, host, user, password)
  exec_sql_command(self, command)
  table_name(self,  record)
  table_exists(self, table_name)
  create_table_from_record(self,  record)
  write_record(self, record)
  read(self,  table_name, start=None)
  seek(self,  table_name, offset=0, origin='current')
  read_range(self,  table_name, start=None, stop=None)
  read_time_range(self,  table_name, start_time=None, stop_time=None)
  delete_table(self,  table_name)
  close(self)
```
Please see [database/mysql_connector.py](mysql_connector.py) for the
semantics of these methods.

## Running

The use of the DatabaseReader and DatabaseWriter from the command line
will typically be via the lister.py script. They operate very much
like other readers and writers, but the command-line arguments might
cause trouble if not used carefully.

Because of the peculiar command-line parsing of listen.py, the reader
and writer will both require the presence of the
```
--database_password <pwd>
```
argument to appear on the command line *before* any DatabaseReader or
DatabaseWriter specification:
```
logger/listener/listen.py \
  --logfile test/NBP1406/s330/raw/NBP1406_s330-2014-08-01 \
  --transform_prefix s330 \
  --transform_parse \
  --database_password rvdas \
  --write_database rvdas@localhost:data
```
The call above reads in sample Seapath 330 data, parses it into all the
different types of messages an S330 emits, and stores records from each
different message type in a different table.

The call below reads records from one of those tables, the one with
message type '$PSXN-23':
```
logger/listener/listen.py \
  --database_password rvdas \
  --database rvdas@localhost:data:S330SpeedKt,S330Latitude,S330Longitude \
  --write_file -
```

## Contributing

Please contact David Pablo Cohn (*david dot cohn at gmail dot com*) - to discuss
opportunities for participating in code development.

## License

This code is made available under the MIT license:

Copyright (c) 2017 David Pablo Cohn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Additional Licenses

