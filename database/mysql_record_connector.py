#!/usr/bin/env python3

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


# Based on https://dev.mysql.com/doc/connector-python/en/connector-python-example-connecting.html

################################################################################
class MySQLRecordConnector:
    # Name of table in which we will store mappings from record field
    # names to the tnames of the tables containing those fields.
    FIELD_NAME_MAPPING_TABLE = 'FIELD_NAME_MAPPING_TABLE'

    def __init__(self, database, host, user, password):
        """Interface to MySQLConnector, to be imported by, e.g. DatabaseWriter."""
        if not MYSQL_ENABLED:
            logging.warning('MySQL not found, so MySQL functionality not available.')
            return

        self.connection = mysql.connector.connect(database=database, host=host,
                                                  user=user, password=password)
        # Map from table_name->next id we're going to read from that table
        self.next_id = {}

        self.exec_sql_command('set autocommit = 1')

    ############################
    def exec_sql_command(self, command):
        # logging.warning('COMMAND: %s', command)
        cursor = self.connection.cursor()
        cursor.execute(command)
        self.connection.commit()
        cursor.close()

    ############################
    def table_name_from_record(self,  record):
        """Infer table name from record."""
        table_name = record.data_id
        if record.message_type:
            table_name += '#' + record.message_type

        # Clean up common, non-SQL-friendly characters
        # table_name = table_name.replace('$','').replace('-','_')
        return table_name

    ############################
    def table_name_from_field(self,  field):
        """Look up which table a particular field is stored in."""

        # If mapping table doesn't exist, then either we've not seen any
        # records yet, or something has gone horribly wrong.
        if not self.table_exists(self.FIELD_NAME_MAPPING_TABLE):
            logging.info('Mapping table "%s" does not exist - is something wrong?')
            return None

        query = 'select table_name from %s where (field_name = "%s")' % \
                (self.FIELD_NAME_MAPPING_TABLE, field)
        logging.debug('executing query "%s"', query)
        cursor = self.connection.cursor()
        cursor.execute(query)
        try:
            return next(cursor)[0]
        except (StopIteration, IndexError):
            return None

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
    TYPE_MAP = {
        int:   'int',
        float: 'double',
        str:   'text',
        bool:  'bool',
    }

    ############################
    def _register_record_fields(self,  record):
        """Add a field_name->table_name entry for each field name in the record
        to the database. This will allow us to look up the right tables to fetch
        when given a list of field names."""

        # Create mapping table if it doesn't exist yet
        if not self.table_exists(self.FIELD_NAME_MAPPING_TABLE):
            table_cmd = 'create table %s (field_name varchar(255) primary key, ' \
                        'table_name tinytext, index(field_name))' \
                        % self.FIELD_NAME_MAPPING_TABLE
            logging.info('Creating table with command: %s', table_cmd)
            self.exec_sql_command(table_cmd)

        # What table does this record type belong to?
        table_name = self.table_name_from_record(record)

        # Iterate through fields in record, figure out their type and
        # create an table type appropriate for each. Skip if a matching
        # field_name already exists.
        for field_name in record.fields:
            if not self.table_name_from_field(field_name):
                write_cmd = 'insert into %s values ("%s", "%s")' % \
                            (self.FIELD_NAME_MAPPING_TABLE, field_name, table_name)
                logging.debug('Inserting record into table with command: %s', write_cmd)
                self.exec_sql_command(write_cmd)

    def value_type(self, value):
        if value is None:
            value = ''  # coerce to a str
        if type(value) not in self.TYPE_MAP:
            logging.error('Unrecognized value type in record: %s', type(value))
            raise TypeError('Unrecognized value type in record: %s', type(value))
        return self.TYPE_MAP[type(value)]

    ############################
    def create_table_from_record(self,  record):
        """Create a new table with one column for each field in the record. Try
        to infer the proper type for each column based on the type of the value
        of the field."""
        if not record:
            return
        table_name = self.table_name_from_record(record)
        if self.table_exists(table_name):
            logging.info('Trying to create table that already exists: %s', table_name)
            return

        # Id and timestamp are needed for all tables
        columns = ['`id` int(11) not null auto_increment',
                   # '`message_type` text',
                   '`timestamp` double not null']

        # Iterate through fields in record, figure out their type and
        # create an table type appropriate for each.
        for field in record.fields:
            value = record.fields[field]
            columns.append('`%s` %s' % (field, self.value_type(value)))

        table_cmd = 'create table `%s` (%s, primary key (`id`), ' \
                    'index(id, timestamp))' % \
                    (table_name, ','.join(columns))
        logging.info('Creating table with command: %s', table_cmd)
        self.exec_sql_command(table_cmd)

        # Register the fields in the record as being contained in this table.
        self._register_record_fields(record)

    ############################
    def write_record(self, record):
        """Write record to table."""

        # Helper function for formatting
        def map_value_to_str(value):
            if value is None:
                return '""'
            elif type(value) in [int, float]:
                return str(value)
            elif type(value) is str:
                return '"%s"' % value
            elif type(value) is bool:
                return '1' if value else '0'
            logging.warning('Found unexpected value type "%s" for "%s"',
                            type(value), value)
            return '""'

        table_name = self.table_name_from_record(record)

        keys = record.fields.keys()
        write_cmd = 'insert into `%s` (`timestamp`,%s) values (%f,%s)' % \
                    (table_name, ','.join(keys), record.timestamp,
                     ','.join([map_value_to_str(record.fields[k]) for k in keys]))

        logging.debug('Inserting record into table with command: %s', write_cmd)
        try:
            self.exec_sql_command(write_cmd)

        # If we've failed because there's some (new) unrecognized column,
        # it means that this record contains fields we've not seen before
        # for this data id. Add those fields as new columns and try again.
        except mysql.connector.errors.ProgrammingError as e:
            if 'Unknown column' in str(e):
                self._add_missing_columns(table_name, record)
                self.exec_sql_command(write_cmd)
            else:
                raise

    def _add_missing_columns(self, table_name, record):
        for field in record.fields.keys():
            value_type = self.value_type(record.fields[field])
            add_cmd = f'alter table {table_name} add column {field} {value_type};'
            try:
                self.exec_sql_command(add_cmd)
            # It's okay if the column already exists
            except mysql.connector.errors.ProgrammingError as e:
                if 'Duplicate column name' not in str(e):
                    raise

    def _parse_table_name(self, table_name):
        """Parse table name into data_id and message_type."""
        if '#' in table_name:
            (data_id, message_type) = table_name.split(sep='#', maxsplit=1)
        else:
            data_id = table_name
            message_type = None
        return (data_id, message_type)

    ############################
    def _get_table_columns(self, table_name):
        """Get columns (we could probably cache these, checking against the
        existence of self.last_record_read[table_name] to know when we
        need to rebuild."""
        cursor = self.connection.cursor()
        cursor.execute('show columns in `%s`' % table_name)
        columns = [c[0] for c in cursor]
        logging.debug('Columns: %s', columns)
        return columns

    ############################
    def _num_rows(self, table_name):
        query = 'select count(1) from `%s`' % table_name
        cursor = self.connection.cursor()
        cursor.execute(query)
        num_rows = next(cursor)[0]
        return num_rows

    ############################
    def _fetch_and_parse_records(self, table_name, query):
        """Fetch records, give DB query, and parse into DASRecords."""

        (data_id, message_type) = self._parse_table_name(table_name)
        columns = self._get_table_columns(table_name)

        cursor = self.connection.cursor()
        cursor.execute(query)

        results = []
        for values in cursor:
            logging.debug('value: %s', values)
            fields = dict(zip(columns, values))
            id = fields.pop('id')
            self.next_id[table_name] = id + 1

            timestamp = fields.pop('timestamp')
            results.append(DASRecord(data_id=data_id, message_type=message_type,
                                     timestamp=timestamp, fields=fields))
        cursor.close()
        return results

    ############################
    def read(self,  table_name, field_list=None, start=None):
        """Read the next record from table. If start is specified, reset read
        to start at that position."""

        if start is None:
            if table_name not in self.next_id:
                self.next_id[table_name] = 1
            start = self.next_id[table_name]

        # If they haven't given us any fields, retrieve everything
        if not field_list:
            fields = '*'
        else:
            fields = 'id,timestamp,' + ','.join(field_list)

        query = 'select %s from `%s` where (id = %d)' % (fields, table_name, start)
        result = self._fetch_and_parse_records(table_name, query)

        if not result:
            return None
        return result[0]

    ############################
    def seek(self,  table_name, offset=0, origin='current'):
        """Behavior is intended to mimic file seek() behavior but with
        respect to records: 'offset' means number of records, and origin
        is either 'start', 'current' or 'end'."""

        if table_name not in self.next_id:
            self.next_id[table_name] = 1

        if origin == 'current':
            self.next_id[table_name] += offset
        elif origin == 'start':
            self.next_id[table_name] = offset + 1
        elif origin == 'end':
            num_rows = self._num_rows(table_name)
            self.next_id[table_name] = num_rows + offset + 1

        logging.debug('Seek: next position table %s %d',
                      table_name, self.next_id[table_name])

    ############################
    def read_range(self,  table_name, field_list=None, start=None, stop=None):
        """Read one or more records from table. If start is not specified,
        begin reading at the next not-yet-read record. If stops is
        not specified, read as many records as are available."""

        if start is None:
            if table_name not in self.next_id:
                self.next_id[table_name] = 1
            start = self.next_id[table_name]

        condition_list = ['id >= %d' % start]
        if stop is not None:
            condition_list.append('id < %d' % stop)
        condition_clause = 'where (%s)' % ' and '.join(condition_list)

        # If they haven't given us any fields, retrieve everything
        if not field_list:
            fields = '*'
        else:
            fields = 'id,timestamp,' + ','.join(field_list)

        query = 'select %s from `%s` %s' % (fields, table_name, condition_clause)
        return self._fetch_and_parse_records(table_name, query)

    ############################
    def read_time_range(self, table_name, field_list=None,
                        start_time=None, stop_time=None):
        """Read one or more records from table. If start_time is not
        specified, begin reading at the earliest record. If stop_time is
        not specified, read to the most recent."""

        condition_list = []
        if start_time is not None:
            condition_list.append('timestamp >= %f' % start_time)
        if stop_time is not None:
            condition_list.append('timestamp < %f' % stop_time)

        if condition_list:
            condition_clause = 'where (%s)' % ' and '.join(condition_list)
        else:
            condition_clause = ''

        # If they haven't given us any fields, retrieve everything
        if not field_list:
            fields = '*'
        else:
            fields = 'id,timestamp,' + ','.join(field_list)

        query = 'select %s from `%s` %s' % (fields, table_name, condition_clause)
        return self._fetch_and_parse_records(table_name, query)

    ############################
    def delete_table(self,  table_name):
        """Delete a table."""
        delete_cmd = 'drop table `%s`' % table_name
        logging.info('Dropping table with command: %s', delete_cmd)
        self.exec_sql_command(delete_cmd)

        # Clear out our recollection of how far into the table we've read
        if table_name in self.next_id:
            del self.next_id[table_name]

        # Delete any references to that table from the file name mapping
        delete_refs = 'delete from %s where table_name = "%s"' % \
                      (self.FIELD_NAME_MAPPING_TABLE, table_name)
        logging.info('Removing table references with command: %s', delete_refs)
        self.exec_sql_command(delete_refs)

    ############################
    def close(self):
        """Close connection."""
        self.connection.close()
