#!/usr/bin/env python3
"""Tables:

  data: pk timestamp field_name field_value source_record

We don't know what type each value will have, so have a column for
int, float, str and bool and leave all but the appropriate value type
NULL. Docs claim that NULL values take no space, so...

Still so many ways we could make this more space efficient, most
obviously by partitioning field_name (and even timestamp?) into
foreign keys.

    field_name - could store this in a separate table so that it's only
      a foreign key in the data table. Something like:

        fields: id field_name field_type

    source_record - an id indexing a table where raw source records are
      stored, so that we can re-parse and recreate whatever data we want
      if needed.

Current implementation is simple and inefficient in both computation
and storage.

TODO: Allow wildcarding field selection, so client can specify 'S330*,Knud*'

"""
import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))
from logger.utils.das_record import DASRecord  # noqa: E402

try:
    import mysql.connector
    MYSQL_ENABLED = True
except ImportError:
    MYSQL_ENABLED = False


################################################################################
class MySQLConnector:
    # Name of table in which we will store mappings from record field
    # names to the tnames of the tables containing those fields.
    DATA_TABLE = 'data'
    FIELD_TABLE = 'fields'
    SOURCE_TABLE = 'source'

    def __init__(self, database, host, user, password,
                 tail=False, save_source=True):
        """Interface to MySQLConnector, to be imported by, e.g. DatabaseWriter."""
        if not MYSQL_ENABLED:
            logging.warning('MySQL not found, so MySQL functionality not available.')
            return

        self.connection = mysql.connector.connect(database=database, host=host,
                                                  user=user, password=password,
                                                  auth_plugin='mysql_native_password')
        self.save_source = save_source

        # What's the next id we're supposed to read? Or if we've been
        # reading by timestamp, what's the last timestamp we've seen?
        self.next_id = 1
        self.last_timestamp = 0

        self.exec_sql_command('set autocommit = 1')

        # Create tables if they don't exist yet
        if not self.table_exists(self.SOURCE_TABLE):
            table_cmd = 'CREATE TABLE %s (id INT PRIMARY KEY AUTO_INCREMENT, ' \
                        'record TEXT)' % self.SOURCE_TABLE
            logging.info('Creating table with command: %s', table_cmd)
            self.exec_sql_command(table_cmd)

        if not self.table_exists(self.DATA_TABLE):
            table_cmd = ['CREATE TABLE %s ' % self.DATA_TABLE,
                         '(',
                         'id INT PRIMARY KEY AUTO_INCREMENT,',
                         'timestamp DOUBLE,',
                         'field_name VARCHAR(255),',
                         'int_value INT,',
                         'float_value DOUBLE,',
                         'str_value TEXT,',
                         'bool_value INT,',
                         'source INT,',
                         'INDEX (timestamp),',
                         'FOREIGN KEY (source) REFERENCES %s(id)'
                         % self.SOURCE_TABLE,
                         ')'
                         ]
            logging.info('Creating table with command: %s', ' '.join(table_cmd))
            self.exec_sql_command(' '.join(table_cmd))

        # Once tables are initialized, seek to end if tail is True
        if tail:
            self.seek(offset=0, origin='end')

    ############################
    def exec_sql_command(self, command):
        cursor = self.connection.cursor()
        try:
            cursor.execute(command)
            self.connection.commit()
            cursor.close()
        except mysql.connector.errors.Error as e:
            logging.error('Executing command: "%s", encountered error "%s"',
                          command, str(e))

    ############################
    def table_exists(self, table_name):
        """Does the specified table exist in the database?"""
        cursor = self.connection.cursor()
        cursor.execute('SHOW TABLES LIKE "%s"' % table_name)
        if cursor.fetchone():
            exists = True
        else:
            exists = False
        cursor.close()
        return exists

    ############################
    def write_record(self, record):
        """Write record to table."""

        # First, check that we've got something we can work with
        if not record:
            return
        if not type(record) == DASRecord:
            logging.error('write_record() received non-DASRecord as input. '
                          'Type: %s', type(record))
            return

        # If we're saving source records, we have to do a little
        # legerdemain: after we've saved the record, we need to retrieve
        # the id of the record we've just saved so that we can attach it
        # to the data values we're about to save.
        if self.save_source:
            write_cmd = 'insert into `%s` (record) values (\'%s\')' % \
                        (self.SOURCE_TABLE, record.as_json())
            logging.debug('Inserting source into table with command: %s', write_cmd)
            self.exec_sql_command(write_cmd)

            # Get the id of the saved source record. Note: documentation
            # *claims* that this is kept on a per-client basis, so it's safe
            # even if another client does an intervening write.
            query = 'select last_insert_id()'
            cursor = self.connection.cursor()
            cursor.execute(query)
            # source_field = ', source'
            source_id = next(cursor)[0]
        else:
            # source_field = ''
            source_id = None

        if not record.fields:
            logging.info('DASRecord has no parsed fields. Skipping record.')
            return

        # Write one row for each field-value pair. Columns are:
        #     timestamp
        #     field_name
        #     int_value   \
        #     float_value, \ Only one of these fields will be non-NULL,
        #     str_value    / depending on the type of the value.
        #     bool_value  /

        timestamp = record.timestamp
        values = []
        for field_name, value in record.fields.items():
            value_array = ['%f' % timestamp, '"%s"' % field_name,
                           'NULL', 'NULL', 'NULL', 'NULL']
            if type(value) is int:
                value_array[2] = '%d' % value
            elif type(value) is float:
                value_array[3] = '%f' % value
            elif type(value) is str:
                value_array[4] = '"%s"' % value
            elif type(value) is bool:
                value_array[5] = '%d' % ('1' if value else '0')
            elif value is None:
                value_array[4] = '""'
            else:
                logging.error('Unknown record value type (%s) for %s: %s',
                              type(value), field_name, value)
                continue

            # If we've saved this field's source record, append source's
            # foreign key to row so we can look it up.
            if source_id:
                value_array.append('%d' % source_id)

            # Join entries into a string, append to list of other values
            # we've already saved.
            value_str = '(%s)' % ','.join(value_array)
            values.append(value_str)

        # Build the SQL query
        fields = ['timestamp',
                  'field_name',
                  'int_value',
                  'float_value',
                  'str_value',
                  'bool_value']
        if source_id:
            fields.append('source')

        if not values:
            logging.warning('No values found in record %s', str(record))

        write_cmd = 'insert into `%s` (%s) values %s' % \
            (self.DATA_TABLE, ','.join(fields), ','.join(values))
        logging.debug('Inserting record into table with command: %s', write_cmd)
        self.exec_sql_command(write_cmd)

    ############################
    def read(self, field_list=None, start=None, num_records=1):
        """Read the next record from table. If start is specified, reset read
        to start at that position."""

        if start is None:
            start = self.next_id
        condition = 'id >= %d' % start

        # If they haven't given us any fields, retrieve everything
        if field_list:
            field_conditions = ['field_name="%s"' % f for f in field_list.split(',')]
            condition += ' and (%s)' % ' or '.join(field_conditions)

        condition += ' order by id'

        if num_records is not None:
            condition += ' limit %d' % num_records

        query = 'select * from `%s` where %s' % (self.DATA_TABLE, condition)
        logging.debug('read query: %s', query)
        return self._process_query(query)

    ############################
    def read_time(self, field_list=None, start_time=None, stop_time=None):
        """Read the next records from table based on timestamps. If start_time
        is None, use the timestamp of the last read record. If stop_time is None,
        read all records since then."""

        if start_time is None:
            condition = 'timestamp > %f' % self.last_timestamp
        else:
            condition = 'timestamp > %f' % start_time

        if stop_time is not None:
            condition = '(%s and timestamp < %f)' % (condition, stop_time)

        # If they haven't given us any fields, retrieve everything
        if field_list:
            field_conditions = ['field_name="%s"' % f for f in field_list]
            condition += ' and (%s)' % ' or '.join(field_conditions)

        condition += ' order by timestamp'

        query = 'select * from `%s` where %s' % (self.DATA_TABLE, condition)
        logging.debug('read query: %s', query)
        return self._process_query(query)

    ############################
    def seek(self, offset=0, origin='current'):
        """Behavior is intended to mimic file seek() behavior but with
        respect to records: 'offset' means number of records, and origin
        is either 'start', 'current' or 'end'."""

        num_rows = self._num_rows(self.DATA_TABLE)

        if origin == 'current':
            self.next_id += offset
        elif origin == 'start':
            self.next_id = offset + 1
        elif origin == 'end':
            self.next_id = num_rows + offset + 1

        self._next_id = min(num_rows, self.next_id)

        logging.debug('Seek: next position %d', self.next_id)

    ############################
    def _num_rows(self, table_name):
        query = 'select count(1) from `%s`' % table_name
        cursor = self.connection.cursor()
        cursor.execute(query)
        num_rows = next(cursor)[0]
        return num_rows

    ############################
    def _process_query(self, query):
        cursor = self.connection.cursor()
        cursor.execute(query)

        results = {}
        for values in cursor:
            (id, timestamp, field_name,
             int_value, float_value, str_value, bool_value,
             source) = values

            if field_name not in results:
                results[field_name] = []

            if int_value is not None:
                val = int_value
            elif float_value is not None:
                val = float_value
            elif str_value is not None:
                val = str_value
            elif float_value is not None:
                val = int_value
            elif bool_value is not None:
                val = bool(bool_value)

            results[field_name].append((timestamp, val))
            self.next_id = id + 1
            self.last_timestamp = timestamp
        cursor.close()
        return results

    ############################
    def delete_table(self,  table_name):
        """Delete a table."""
        delete_cmd = 'drop table `%s`' % table_name
        logging.info('Dropping table with command: %s', delete_cmd)
        self.exec_sql_command(delete_cmd)

    ############################
    def close(self):
        """Close connection."""
        self.connection.close()
