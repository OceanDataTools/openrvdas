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
import json

sys.path.append('.')
from logger.utils.das_record import DASRecord  # noqa: E402

try:
    import pymongo
    MONGO_ENABLED = True
except ImportError:
    MONGO_ENABLED = False


################################################################################
class MongoConnector:
    # Name of table in which we will store mappings from record field
    # names to the tnames of the tables containing those fields.
    DATA_TABLE = 'data'
    FIELD_TABLE = 'fields'
    SOURCE_TABLE = 'source'

    def __init__(self, database, host, user, password,
                 tail=False, save_source=True):
        """Interface to MongoConnector, to be imported by, e.g. DatabaseWriter."""
        if not MONGO_ENABLED:
            logging.warning('MongoClient not found, so MongoDB functionality not available.')
            return

        self.client = pymongo.MongoClient([host])
        self.db = self.client[database]

        self.save_source = save_source

        # What's the next id we're supposed to read? Or if we've been
        # reading by timestamp, what's the last timestamp we've seen?
        self.next_id = 0
        self.last_timestamp = None

        # Create tables if they don't exist yet
        if self.SOURCE_TABLE not in self.db.collection_names():
            self.db[self.SOURCE_TABLE]

        if self.DATA_TABLE not in self.db.collection_names():
            self.db[self.DATA_TABLE]

    ############################
    def write_record(self, record):
        """Write record to table."""

        # First, check that we've got something we can work with
        if not record:
            return

        if type(record) is not DASRecord:
            logging.error('write_record() received non-DASRecord as input. '
                          'Type: %s', type(record))
            return

        # If we're saving source records, we have to do a little
        # legerdemain: after we've saved the record, we need to retrieve
        # the id of the record we've just saved so that we can attach it
        # to the data values we're about to save.
        if self.save_source:
            logging.debug('Inserting source into table')
            logging.debug(record)

            result = self.db[self.SOURCE_TABLE].insert_one(json.loads(record.as_json()))

            # Get the id of the saved source record. Note: documentation
            # *claims* that this is kept on a per-client basis, so it's safe
            # even if another client does an intervening write.
            source_id = result.inserted_id
        else:
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

        values = []
        for field_name, value in record.fields.items():
            data_record = {
                'timestamp': record.timestamp,
                'field_name': field_name,
                'int_value': None,
                'float_value': None,
                'str_value': None,
                'bool_value': None,
                'source_id': None
            }

            if type(value) is int:
                data_record['int_value'] = value
            elif type(value) is float:
                data_record['float_value'] = value
            elif type(value) is str:
                data_record['str_value'] = value
            elif type(value) is bool:
                data_record['bool_value'] = True if value else False
            elif value is None:
                data_record['str_value'] = '""'
            else:
                logging.error('Unknown record value type (%s) for %s: %s',
                              type(value), field_name, value)
                continue

            # If we've saved this field's source record, append source's
            # foreign key to row so we can look it up.
            if source_id:
                data_record['source_id'] = source_id

            # Join entries into a string, append to list of other values
            # we've already saved.
            values.append(data_record)

        # Build the SQL query
        # fields = ['timestamp',
        #           'field_name',
        #           'int_value',
        #           'float_value',
        #           'str_value',
        #           'bool_value']
        # if source_id:
        #   fields.append('source')

        if not values:
            logging.warning('No values found in record %s', str(record))

        # write_cmd = 'insert into `%s` (%s) values %s' % \
        #               (self.DATA_TABLE, ','.join(fields), ','.join(values))
        logging.debug('Inserting record into table')
        result = self.db[self.DATA_TABLE].insert_many(values)

        # self.exec_sql_command(write_cmd)

    ############################
    def read(self, field_list=None, start=None, num_records=1):
        """Read the next record from table. If start is specified, reset read
        to start at that position."""

        query = {}
        projection = {'_id': 0}

        if start is None:
            start = self.next_id

        # If they haven't given us any fields, retrieve everything
        if field_list:
            query['field_name'] = {"$in": field_list.split(',')}

        if num_records is None:
            limit = 0
        else:
            limit = num_records

        # query = 'select * from `%s` where %s' % (self.DATA_TABLE, condition)
        results = list(self.db[self.DATA_TABLE].find(query, projection).skip(start).limit(limit))

        if len(results) == 0:
            return {}

        output = {}
        for result in results:

            if result['field_name'] not in output:
                output[result['field_name']] = []

            if result['int_value'] is not None:
                output[result['field_name']].append((result['timestamp'], result['int_value']))
            elif result['float_value'] is not None:
                output[result['field_name']].append((result['timestamp'], result['float_value']))
            elif result['str_value'] is not None:
                output[result['field_name']].append((result['timestamp'], result['str_value']))
            elif result['bool_value'] is not None:
                output[result['field_name']].append((result['timestamp'], result['bool_value']))
            else:
                output[result['field_name']].append((result['timestamp']))

        self.next_id = start + len(results)

        return output
        # return self._process_query(query)

    ############################
    def read_time(self, field_list=None, start_time=None, stop_time=None):
        """Read the next records from table based on timestamps. If start_time
        is None, use the timestamp of the last read record. If stop_time is None,
        read all records since then."""

        query = {}

        if start_time or stop_time:
            query['timestamp'] = {}

        if start_time is not None:
            query['timestamp']['$gte'] = start_time

        if stop_time is not None:
            query['timestamp']['$lte'] = stop_time

        # If they haven't given us any fields, retrieve everything
        if field_list:
            query['field_name'] = {"$in": {field_list.split(',')}}

        sort = {'timestamp': -1}

        logging.debug('read query: %s', query)
        return self.db[self.DATA_TABLE].find(query).sort(sort).toArray()

    ############################
    def seek(self, offset=0, origin='current'):
        """Behavior is intended to mimic file seek() behavior but with
        respect to records: 'offset' means number of records, and origin
        is either 'start', 'current' or 'end'."""

        num_rows = self.db[self.DATA_TABLE].count()

        if origin == 'current':
            self.next_id += offset
        elif origin == 'start':
            self.next_id = offset
        elif origin == 'end':
            self.next_id = num_rows + offset

        self._next_id = min(num_rows, self.next_id)

        logging.debug('Seek: next position %d', self.next_id)

    ############################
    # def _num_rows(self, table_name):
    #   query = 'select count(1) from `%s`' % table_name
    #   cursor = self.connection.cursor()
    #   cursor.execute(query)
    #   num_rows = next(cursor)[0]
    #   return num_rows

    ############################
    # def _process_query(self, query):
    #   cursor = self.connection.cursor()
    #   cursor.execute(query)

    #   results = {}
    #   for values in cursor:
    #     (id, timestamp, field_name,
    #      int_value, float_value, str_value, bool_value,
    #      source) = values

    #     if field_name not in results:
    #       results[field_name] = []

    #     if int_value is not None:
    #       val = int_value
    #     elif float_value is not None:
    #       val = float_value
    #     elif str_value is not None:
    #       val = str_value
    #     elif float_value is not None:
    #       val = int_value
    #     elif bool_value is not None:
    #       val = bool(bool_value)

    #     results[field_name].append((timestamp, val))
    #     self.next_id = id + 1
    #     self.last_timestamp = timestamp
    #   cursor.close()
    #   return results

    ############################
    def delete_table(self,  table_name):
        """Delete a table."""
        # delete_cmd = 'drop table `%s`' % table_name
        logging.info('Dropping table')

        return self.db[table_name].drop()

        # self.exec_sql_command(delete_cmd)

    ############################
    def close(self):
        """Close connection."""
        # self.connection.close()
        self.client.close()
