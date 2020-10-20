#!/usr/bin/env python3

import logging
import datetime
import sys
import json

sys.path.append('.')
from logger.utils.das_record import DASRecord  # noqa: E402

try:
    import pymongo
    MONGO_ENABLED = True
except ImportError:
    MONGO_ENABLED = False

# Based on https://dev.mysql.com/doc/connector-python/en/connector-python-example-connecting.html


################################################################################
class MongoRecordConnector:
    # Name of table in which we will store mappings from record field
    # names to the tnames of the tables containing those fields.
    FIELD_NAME_MAPPING_TABLE = 'FIELD_NAME_MAPPING_TABLE'

    def __init__(self, database, host, user, password):
        """Interface to MongoConnector, to be imported by, e.g. DatabaseWriter."""
        if not MONGO_ENABLED:
            logging.warning('MongoDB not found, so Mongo functionality not available.')
            return

        self.client = pymongo.MongoClient(host)
        self.db = self.client[database]

        # Map from table_name->next id we're going to read from that table
        self.next_id = {}

        # self.exec_sql_command('set autocommit = 1')

    # ############################
    # def exec_sql_command(self, command):
    #   cursor = self.connection.cursor()
    #   cursor.execute(command)
    #   self.connection.commit()
    #   cursor.close()

    ############################
    def table_name_from_record(self,  record):
        """Infer table name from record."""
        table_name = record.data_id
        if record.message_type:
            table_name += '#' + record.message_type

        # Clean up common, non-SQL-friendly characters
        table_name = table_name.replace('$', '').replace('-', '_')
        return table_name

    ############################
    def table_name_from_field(self,  field):
        """Look up which table a particular field is stored in."""

        # If mapping table doesn't exist, then either we've not seen any
        # records yet, or something has gone horribly wrong.
        if self.FIELD_NAME_MAPPING_TABLE not in self.db.collection_names():
            logging.info('Mapping table "%s" does not exist - is something wrong?',
                         self.FIELD_NAME_MAPPING_TABLE)
            return None

        result = self.db[self.FIELD_NAME_MAPPING_TABLE].find_one({}, {"_id": 0})

        if result is not None:
            return self.FIELD_NAME_MAPPING_TABLE
        else:
            return None

        # query = 'select table_name from %s where (field_name = "%s")' % \
        #         (self.FIELD_NAME_MAPPING_TABLE, field)
        # logging.debug('executing query "%s"', query)
        # cursor = self.connection.cursor()
        # cursor.execute(query)
        # try:
        #   return next(cursor)[0]
        # except (StopIteration, IndexError):
        #   return None

    ############################
    def table_exists(self, table_name):
        """Does the specified table exist in the database?"""
        return table_name in self.db.collection_names()

        # cursor = self.connection.cursor()
        # cursor.execute('SHOW TABLES LIKE "%s"' % table_name)
        # if cursor.fetchone():
        #   exists = True
        # else:
        #   exists = False
        # cursor.close()
        # return exists

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
            self.db[self.FIELD_NAME_MAPPING_TABLE]
            # table_cmd = 'create table %s (field_name varchar(255) primary key, ' \
            #             'table_name tinytext, index(field_name))' \
            #             %  self.FIELD_NAME_MAPPING_TABLE
            # logging.info('Creating table with command: %s', table_cmd)
            # self.exec_sql_command(table_cmd)

        # What table does this record type belong to?
        table_name = self.table_name_from_record(record)

        # Iterate through fields in record, figure out their type and
        # create an table type appropriate for each. Skip if a matching
        # field_name already exists.
        for field_name in record.fields:
            if not self.table_name_from_field(field_name):

                # write_cmd = 'insert into %s values ("%s", "%s")' % \
                #             (self.FIELD_NAME_MAPPING_TABLE, field_name, table_name)
                # logging.debug('Inserting record into table with command: %s', write_cmd)
                self.db[self.FIELD_NAME_MAPPING_TABLE].insert_one(
                    {"field_name": field_name, "table_name": table_name})
                # self.exec_sql_command(write_cmd)

    # ---- This is where I left off ---- #
    ############################
    def create_table_from_record(self,  record):
        """Create a new table with one column for each field in the record. Try
        to infer the proper type for each column based on the type of the value
        of the field."""
        if not record:
            return

        table_name = self.table_name_from_record(record)

        if self.table_exists(table_name):
            logging.warning('Trying to create table that already exists: %s',
                            table_name)
            return

        logging.info('Creating table: %s', table_name)
        self.db.create_collection(table_name)

        # # Id and timestamp are needed for all tables
        # columns = ['`id` int(11) not null auto_increment',
        #            # '`message_type` text',
        #            '`timestamp` double not null']

        # # Iterate through fields in record, figure out their type and
        # # create an table type appropriate for each.
        # for field in record.fields:
        #   value = record.fields[field]
        #   if value is None:
        #     value = ''
        #   if not type(value) in self.TYPE_MAP:
        #     logging.error('Unrecognized value type in record: %s', type(value))
        #     logging.error('Record: %s', str(record))
        #     raise TypeError('Unrecognized value type in record: %s', type(value))
        #   columns.append('`%s` %s' %( field, self.TYPE_MAP[type(value)]))

        # table_cmd = 'create table `%s` (%s, primary key (`id`), ' \
        #             'index(id, timestamp))' % \
        #             (table_name, ','.join(columns))
        # logging.info('Creating table with command: %s', table_cmd)
        # self.exec_sql_command(table_cmd)

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

        logging.debug('Inserting record into table: %s', table_name)
        # logging.debug('Record: %s', record)
        self.db[table_name].insert_one(json.loads(record.as_json()))

        # keys = record.fields.keys()
        # write_cmd = 'insert into `%s` (`timestamp`,%s) values (%f,%s)' % \
        #             (table_name, ','.join(keys), record.timestamp,
        #              ','.join([map_value_to_str(record.fields[k]) for k in keys]))

        # logging.debug('Inserting record into table with command: %s', write_cmd)
        # self.exec_sql_command(write_cmd)

    ############################
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

        result = self.db[table_name].find_one()
        if result is not None:
            columns = []
            for k, v in result:
                columns.append(k)

        # cursor = self.connection.cursor()
        # cursor.execute('show columns in `%s`' % table_name)
        # columns = [c[0] for c in cursor]
        logging.debug('Columns: %s', columns)
        return columns

    ############################
    def _num_rows(self, table_name):
        num_rows = self.db[table_name].count()
        # query = 'select count(1) from `%s`' % table_name
        # cursor = self.connection.cursor()
        # cursor.execute(query)
        # num_rows = next(cursor)[0]
        return num_rows

    ############################
    def _fetch_and_parse_records(self, table_name, query):
        """Fetch records, give DB query, and parse into DASRecords."""

        cursor = list(self.db[table_name].find(query, {'_id': 0}))
        (data_id, message_type) = self._parse_table_name(table_name)
        columns = self._get_table_columns(table_name)

        # cursor = self.connection.cursor()
        # cursor.execute(query)

        results = []
        for values in cursor:
            fields = dict(zip(columns, values))
            # id = fields.pop('id')
            self.next_id[table_name] = self.next_id[table_name] + 1

            timestamp = fields.pop('timestamp')
            results.append(DASRecord(data_id=data_id, message_type=message_type,
                                     timestamp=timestamp, fields=fields))
        # cursor.close()
        return results

    ############################
    def read(self,  table_name, field_list=None, start=None):
        """Read the next record from table. If start is specified, reset read
        to start at that position."""

        query = {}
        projection = {'_id': 0}

        if start is None:
            if table_name not in self.next_id:
                self.next_id[table_name] = 0

            start = self.next_id[table_name]

        if field_list:
            for field in field_list:
                projection[field] = 1

        result = list(self.db[table_name].find(query, projection).skip(start).limit(1))

        if len(result) == 0:
            return None

        self.next_id[table_name] = start + 1

        return DASRecord(data_id=result[0]['data_id'], message_type=result[0]['message_type'],
                         timestamp=result[0]['timestamp'], fields=result[0]['fields'])

    ############################
    def seek(self,  table_name, offset=0, origin='current'):
        """Behavior is intended to mimic file seek() behavior but with
        respect to records: 'offset' means number of records, and origin
        is either 'start', 'current' or 'end'."""

        if table_name not in self.next_id:
            self.next_id[table_name] = 0

        if origin == 'current':
            self.next_id[table_name] += offset
        elif origin == 'start':
            self.next_id[table_name] = offset
        elif origin == 'end':
            num_rows = self._num_rows(table_name)
            self.next_id[table_name] = num_rows + offset

        logging.debug('Seek: next position table %s %d',
                      table_name, self.next_id[table_name])

    ############################
    def read_range(self,  table_name, field_list=None, start=None, stop=None):
        """Read one or more records from table. If start is not specified,
        begin reading at the next not-yet-read record. If stops is
        not specified, read as many records as are available."""

        if start is None:
            if table_name not in self.next_id:
                self.next_id[table_name] = 0
            start = self.next_id[table_name]

        if stop is None:
            stop = 0

        projection = {'_id': 0}

        if field_list:
            for field in field_list:
                projection[field] = 1

        results = list(self.db[table_name].find({}, projection).skip(start).limit(stop))

        return results

    ############################
    def read_time_range(self, table_name, field_list=None,
                        start_time=None, stop_time=None):
        """Read one or more records from table. If start_time is not
        specified, begin reading at the earliest record. If stop_time is
        not specified, read to the most recent."""

        projection = {'_id': 0}

        if field_list:
            for field in field_list:
                projection[field] = 1

        query = {}

        if start_time is not None or stop_time is not None:

            query.timestamp = {}

            if start_time is not None:
                startTS = datetime.datetime(start_time)
                query['timestamp']['$gte'] = startTS

            if stop_time is not None:
                stopTS = datetime.datetime(stop_time)
                query['timestamp']['$lt'] = stopTS

        results = self.db[table_name].find(query, projection)

        return results

    ############################
    def delete_table(self,  table_name):
        """Delete a table."""
        # delete_cmd = 'drop table `%s`' % table_name
        logging.info('Dropping table: %s', table_name)
        self.db[table_name].drop()
        # self.exec_sql_command(delete_cmd)

        # Clear out our recollection of how far into the table we've read
        if table_name in self.next_id:
            del self.next_id[table_name]

        # Delete any references to that table from the file name mapping
        query = {"table_name": table_name}
        self.db[self.FIELD_NAME_MAPPING_TABLE].delete_many(query)

        logging.info('Removing table references')
        # self.exec_sql_command(delete_refs)

    ############################
    def close(self):
        """Close connection."""
        self.client.close()
