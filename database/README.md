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
below in "Connector Class Methods"

## Installation

The first step is to copy the distribution file
[database/settings.py.dist](settings.py.dist)
over to [database/settings.py](settings.py). From there, the steps needed to use the
DatabaseReader and DatabaseWriter depend on which database you intend
to use them with. Below, we describe how to set the system up to use
MySQLConnector.

### MySQLConnector

If you have already installed the files needed to run the core
OpenRVDAS code, as described in [the parent directory
INSTALL.md](../INSTALL.md), there are only a couple more steps needed
to get the database working:

1. Install the MySQL server and its client tools
```
  apt-get install mysql-server libmysqlclient-dev # ubuntu

  yum install mariadb-server mariadb-devel mariadb-libs # CentOS
  service mariadb start  # to start db server
  sudo systemctl enable httpd.service # to make it start on boot
```
2. Install the python mysql-connector modules
```
  pip3 install mysqlclient mysql-connector==2.1.6
```
3. Run the configuration script that will create 'test' and 'data'
databases and will create an sql user that has access to those databases.
It will also create a 'test' user that has access only to 'test'.
```
  database/setup_mysql_connector.sh <mysql_user> <mysql_user_pwd>  # ubuntu

  database/setup_mariadb_connector.sh <mysql_user> <mysql_user_pwd>  # CentOS
```
(Note: The script will ask for the root MySQL password.)

At this point you should be able to test the installation by running the
database/test_mysql_connector.py script (to test the mysql_connector)
and logger/writers/test_database_writer.py script (to ensure that it has
been properly connected to the DatabaseWriter).

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
  --logfile test/NBP1700/s330/raw/NBP1700_s330-2017-11-04 \
  --transform_prefix s330 \
  --transform_parse_nmea \
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
  --database rvdas@localhost:data:s330:\$PSXN-23 \
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

