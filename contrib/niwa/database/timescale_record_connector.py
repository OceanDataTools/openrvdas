#!/usr/bin/env python3

import logging
import sys
import json

from os.path import dirname, realpath
from datetime import datetime, timezone


sys.path.append(dirname(dirname(realpath(__file__))))
from logger.utils.das_record import DASRecord

TIMESCALEDB_ENABLED = True
try:
    # import psycopg2.connector
    import psycopg2
    from psycopg2 import sql
    from psycopg2 import extensions as ext

    TIMESCALEDB_ENABLED = True
except ImportError as e:
    logging.error(e)
    TIMESCALEDB_ENABLED = False


# Based on https://dev.POSTGRESQL.com/doc/connector-python/en/connector-python-example-connecting.html

################################################################################
class TimescaledbConnector:
    # Name of table in which we will store mappings from record field
    # names to the hstore key
    FIELD_NAME_MAPPING_TABLE = 't_measurement'
    # TODO: read this from settings file or active flag in DB
    PLATFORM_ID = 4
    #niwa DAS db uses a single table for all values
    MAIN_DATA_TABLE = 't_reading_hstore_sec'
    DEBUG_LOGGING = False

    def __init__(self, database, host, user, password, tail=False, save_source=True, save_metadata=False, debug_logging=False):
        """Interface to postgresqlConnector, to be imported by, e.g. DatabaseWriter."""
        if not TIMESCALEDB_ENABLED:
            logging.warning('postgresql not found, so postgresql functionality not available.')
            return

        try:
            self.connection = psycopg2.connect(database=database, host=host,
                                           user=user, password=password)
            logging.info('Database connected on to "%s" on host: %s', database, host)
        except Exception as e:
            logging.warning('Could not connect to database "%s" on host: %s with exception: %s', database, host, e)

        self.save_source = save_source
        self.save_metadata = save_metadata
        self.tail = tail
        self.DEBUG_LOGGING = debug_logging

        # Map from table_name->next id we're going to read from that table
        self.next_id = {}

        # self.exec_sql_command('set autocommit = 1')

    ############################
    def exec_sql_command(self, command, data=[]):
        with self.connection.cursor() as cursor:
            try:
                if self.DEBUG_LOGGING:
                    logging.debug(cursor.mogrify(command, data))
                cursor.execute(command, data)
                self.connection.commit()
            except psycopg2.errors.DuplicateColumn:
                raise
            except psycopg2.errors.UndefinedColumn:
                logging.warning('Executing command: "%s", encountered programming error: one or more columns do not exist',
                                command.as_string(self.connection))
                raise
            except psycopg2.errors.UndefinedTable:
                logging.warning('Executing command: "%s", encountered programming error: table does not exist',
                              command.as_string(self.connection))
                raise
            except Exception as e:
                logging.error('Executing command: "%s", encountered error "%s"',
                              command.as_string(self.connection), str(e))
                raise
    

    def query_db(self, command, data=[]): 
        cursor = self.connection.cursor()

        try:
            # TODO: make debug logs an option on dasdb logger config
            #logging.debug(cursor.mogrify(command, data))
            cursor.execute(command, data)
            self.connection.commit()
            try:
                result = [row for row in cursor]
                return result
            except psycopg2.ProgrammingError:
                return None

        except psycopg2.errors.DuplicateColumn as e:
            raise e
        except psycopg2.errors.UndefinedColumn as e:
            logging.warning('Executing command: "%s", encountered programming error: one or more columns do not exist',
                            command.as_string(self.connection))
            raise e
        except psycopg2.errors.UndefinedTable as e:
            logging.warning('Executing command: "%s", encountered programming error: table does not exist',
                            command.as_string(self.connection))
            raise e
        except Exception as e:
            logging.error('Executing command: "%s", encountered error "%s"',
                            command.as_string(self.connection), str(e))
            raise e


    def get_measurement_keys(self, instrument_key, measurement_codes):
        query = sql.SQL("SELECT measurement_code, measurement_key FROM t_measurement \
            WHERE instrument_key = %s \
            AND measurement_code IN %s")
        params = (instrument_key, measurement_codes)
        existing_keys = self.query_db(query, params)

        key_map = {}

        for row in existing_keys:
            key_map[row[0]] = row[1]

        return key_map


    def get_new_instrument_key(self, platform_id):
        query = sql.SQL("SELECT instrument_key FROM t_instrument WHERE instrument_key::CHAR like '%s%%' \
            ORDER BY instrument_key DESC LIMIT 1")
        query_params = (platform_id,)
        
        return self.make_new_key_from_platform(platform_id, query, query_params)


    def get_new_measurement_key(self, platform_id):
        query = sql.SQL("SELECT measurement_key FROM t_measurement WHERE measurement_key::CHAR like '%s%%' \
            ORDER BY measurement_key DESC LIMIT 1")
        query_params = (platform_id,)
        
        return self.make_new_key_from_platform(platform_id, query, query_params)


    def make_new_key_from_platform(self, platform_id, query, query_params):
        # return key in format {platform_key}{int} to avoid overlapping measurements added on another platform
        platform_id_str = str(platform_id)
        next_available = "0"

        try:
            last_used_key = self.query_db(query, query_params)[0][0]
            value_without_platform = str(last_used_key).replace(platform_id_str, "", 1)

            # TODO: tidy this up
            if value_without_platform.replace("9", "") == "":
                # if the existing key is {platform_id}9 we want {platform_id}00 for the new one
                next_available = "0" * (len(value_without_platform) + 1)
            # elif value_without_platform[-1] == "0":
            #     # if the existing key is {platform_id}00 we want {platform_id}01
            #     next_available = "0" * (len(value_without_platform) - 1) + "1"
            elif len(str(int(value_without_platform))) != len(value_without_platform):
                # there are leading 0s
                if value_without_platform[-1] == "9" and value_without_platform[-2] == "0":
                    # 1 less 0 than there was as 9 becomes 10
                    next_available = "0" * (len(value_without_platform) - len(str(int(value_without_platform))) -1 )\
                      + str(int(value_without_platform) + 1)
                else:
                    next_available = "0" * (len(value_without_platform) - len(str(int(value_without_platform))))\
                      + str(int(value_without_platform) + 1)
            else:
                # if it's {platform_id}3 etc. just continue the sequence
                next_available = str(int(value_without_platform) + 1)

        except IndexError:
            # no existing value found beginning with this platform_id
            pass
        
        new_value = int(platform_id_str + next_available)
        return new_value


    def insert_new_instrument_if_not_exists(self, platform_id, instrument_code):
        exists_query = sql.SQL("SELECT instrument_key FROM t_instrument WHERE platform_id = %s \
            AND instrument_code = %s LIMIT 1;")
        exists_params = (platform_id, instrument_code)
        
        try:
            existing_key = self.query_db(exists_query, exists_params)[0][0]
            return existing_key
        except IndexError:
            new_key = self.get_new_instrument_key(platform_id)

            # 11 = Unknown person           
            data = (new_key, instrument_code, instrument_code, 11, platform_id, True)
            insert_cmd = sql.SQL("INSERT INTO \
                t_instrument(instrument_key, instrument_name, instrument_code, person_key, platform_id, active)\
                VALUES ({placeholders});").format(placeholders=sql.SQL(', ').join(sql.Placeholder() * len(data)))

            self.query_db(insert_cmd, data)
            return new_key


    def insert_new_measurement_if_not_exists(self, platform_id, instrument_key, measurement_code, metadata):
        exists_query = sql.SQL("SELECT measurement_key FROM t_measurement WHERE instrument_key = %s \
            AND measurement_code = %s LIMIT 1;")
        exists_params = (instrument_key, measurement_code)

        try:
            existing_key = self.query_db(exists_query, exists_params)[0][0]
            return existing_key
        except IndexError:
            new_key = self.get_new_measurement_key(platform_id)

            data = (new_key, measurement_code, datetime.today().strftime('%Y-%m-%d'), metadata["fields"][measurement_code].get("units", None), metadata["fields"][measurement_code].get("description", None), instrument_key)
            insert_cmd = sql.SQL("INSERT INTO \
                t_measurement (measurement_key, measurement_code, date_from, unit, notes, instrument_key)\
                VALUES ({placeholders});").format(placeholders=sql.SQL(', ').join(sql.Placeholder() * len(data)))

            self.query_db(insert_cmd, data)
            return new_key


    def table_exists(self, table_name):
        """Does the specified table exist in the database?"""
        exists_cmd = sql.SQL("SELECT * FROM pg_tables WHERE schemaname='public' and tablename=%s;")
        data = [table_name]
        with self.connection.cursor() as cursor:
            try:
                cursor.execute(exists_cmd, data)
                if cursor.fetchone():
                    exists = True
                else:
                    exists = False
            except psycopg2.errors.UndefinedColumn:
                self.connection.rollback()
                exists = False
                pass
        return exists


    TYPE_MAP = {
        int: 'int',
        float: 'double precision',
        str: 'text',
        bool: 'bool',
        bytearray: 'bytea'
    }

    ############################
    def create_table_from_record(self, record):
        """Create a new table with one column for each field in the record. Try
    to infer the proper type for each column based on the type of the value
    of the field."""
        if not record:
            return
        table_name = record.data_id.lower()
        # if self.table_exists(table_name):
        #   logging.warning('Trying to create table that already exists: %s',
        #                   table_name)
        #   return

        # Id and timestamp are needed for all tables
        columns = []
        columns.append(sql.SQL("{} {}").format(sql.Identifier('id'), sql.SQL('bigint GENERATED ALWAYS AS IDENTITY')))
        columns.append(sql.SQL("{} {}").format(sql.Identifier('timestamp'), sql.SQL('timestamp with time zone not null PRIMARY KEY')))
        columns.append(sql.SQL("{} {}").format(sql.Identifier('metadata'), sql.SQL('jsonb')))


        # Iterate through fields in record, figure out their type and
        # create a table type appropriate for each.
        for x in record.fields:
            value = record.fields[x]
            if value is None:
                value = ''
            if not type(value) in self.TYPE_MAP:
                logging.error('Unrecognized value type in record: %s', type(value))
                logging.error('Record: %s', str(record))
                raise TypeError('Unrecognized value type in record: %s', type(value))
            columns.append(sql.SQL("{} {}").format(sql.Identifier(x.lower()), sql.SQL(self.TYPE_MAP[type(value)])))

        table_cmd = sql.SQL("CREATE TABLE %s ({field});" % ext.quote_ident(table_name, self.connection)).format(
            field=sql.SQL(', ').join(columns))

        logging.info('Creating table with command: %s', table_cmd)
        self.exec_sql_command(table_cmd)

        # Make table into TimeScaleDB Hypertable with timestamp as the partitioning column
        hypertable_cmd = sql.SQL("SELECT create_hypertable((%s), 'timestamp');")
        data = [table_name]
        logging.info('Creating timescale hypertable with command: %s', hypertable_cmd)
        self.exec_sql_command(hypertable_cmd, data)

        if self.tail:
            self.seek(table_name, offset=0, origin='end')

        # index_cmd = 'CREATE INDEX index ON "%s"(timestamp)' % table_name
        # self.exec_sql_command(index_cmd)
        # Register the fields in the record as being contained in this table.
        self._register_record_fields(record)


     ############################
    def write_record(self, record):
        """Write record to table."""
        # timer | value | time_mark
        
        # Helper function for formatting
        def map_value_to_str(value):
            if value is None:
                return '""'
            elif type(value) in [int, float]:
                return str(value)
            elif type(value) is str:
                return "'%s'" % value
            elif type(value) is bool:
                return '1' if value else '0'
            logging.warning('Found unexpected value type "%s" for "%s"',
                            type(value), value)
            return '""'

        # TODO: cache these things
        instrument_code = record.data_id.lower()
        instrument_key = self.insert_new_instrument_if_not_exists(self.PLATFORM_ID, instrument_code)

        keys = ['timer', 'values_sec']

        data_keys = tuple(key for key in record.fields.keys())
        known_keys = self.get_measurement_keys(instrument_key, data_keys)

        hstore_rows = []
        for [field_name, value] in record.fields.items():
            
            measurement_key = known_keys.get(field_name, None)
            if measurement_key is None:
                measurement_key = self.insert_new_measurement_if_not_exists(self.PLATFORM_ID, instrument_key, field_name, record.metadata)

            hstore_rows.append(f'"{measurement_key}" => "{value}"')


        # if self.save_metadata:
        #     keys.append('metadata')
        hstore_value = ', '.join(hstore_rows)
        date_obj = datetime.fromtimestamp(record.timestamp)

        write_cmd = sql.SQL(
            "INSERT INTO " + self.MAIN_DATA_TABLE + " ({fields}) VALUES ({placeholders}) ON CONFLICT (timer) DO UPDATE SET values_sec = " + self.MAIN_DATA_TABLE + ".values_sec || excluded.values_sec;").format(
            fields=sql.SQL(', ').join(map(sql.Identifier, keys)),
            placeholders=sql.SQL(', ').join(sql.Placeholder() * len(keys)))
        
        data = [date_obj, hstore_value]
        #TODO: decide how metadata is handled
        #if self.save_metadata:
        #    data.append(json.JSONEncoder().encode(record.metadata))

        logging.debug('Inserting record into table with command: %s', self.connection.cursor().mogrify(write_cmd, data))
        try:
            self.exec_sql_command(write_cmd, data)
        
        except Exception as e:
            raise

    ############################

    def calculate_time_mark(self, date):
        """
        function to return a string that is a representation of the time during the day
        """

        hour = date.hour
        minute = date.minute

        if minute == 0:
            if hour == 0:
                return '1440'   # midnight
            if hour == 12:
                return '720'    # midday
            return '60'         # exact hour
        if minute == 30:
            return '30'         # half hour
        if minute % 15 == 0:
            return '15'         # quarter hour
        if minute % 10 == 0:
            return '10'         # 10 mins
        if minute % 5 == 0:
            return '5'          # 5 mins
        if minute % 2 == 0:
            return '2'          # even mins
        return '1'              # odd mins



    # NOTE: only used for field mapping tables
    def _table_name_from_field(self, field):
        """Look up which table a particular field is stored in."""

        # If mapping table doesn't exist, then either we've not seen any
        # records yet, or something has gone horribly wrong.
        if not self.table_exists(self.FIELD_NAME_MAPPING_TABLE):
            logging.info('Mapping table "%s" does not exist - is something wrong?')
            return None

        query = sql.SQL("SELECT table_name FROM %s where (field_name = %%s);"
                        % ext.quote_ident(self.FIELD_NAME_MAPPING_TABLE, self.connection))
        data = [field.lower()]
        logging.debug('executing query "%s"', query)
        cursor = self.connection.cursor()
        cursor.execute(query, data)
        try:
            return next(cursor)[0]
        except (StopIteration, IndexError):
            return None

    ############################
    def _register_record_fields(self, record):
        """Add a field_name->table_name entry for each field name in the record
    to the database. This will allow us to look up the right tables to fetch
    when given a list of field names."""

        # Create mapping table if it doesn't exist yet
        if not self.table_exists(self.FIELD_NAME_MAPPING_TABLE):
            table_cmd = sql.SQL("CREATE TABLE %s (field_name varchar(255) primary key, table_name text)"
                                % ext.quote_ident(self.FIELD_NAME_MAPPING_TABLE, self.connection))
            logging.info('Creating field_mapping table with command: %s', table_cmd)
            self.exec_sql_command(table_cmd)

        # What table does this record type belong to?
        table_name = record.data_id.lower()

        # Iterate through fields in record, figure out their type and
        # create an table type appropriate for each. Skip if a matching
        # field_name already exists.
        for field_name in record.fields:
            field_name=field_name.lower()
            if not self._table_name_from_field(field_name):
                write_cmd = sql.SQL("INSERT INTO %s ({field}, {table}) VALUES (%%s, %%s);"
                                    % ext.quote_ident(self.FIELD_NAME_MAPPING_TABLE, self.connection)).format(
                    field=sql.Identifier('field_name'),
                    table=sql.Identifier('table_name'))
                data = [field_name, table_name]
                logging.debug('Inserting record into table with command: %s', write_cmd)
                self.exec_sql_command(write_cmd, data)

    ############################
    def _add_missing_columns(self, table_name, record):
        for field_name in record.fields:
            value = record.fields[field_name]
            if value is None:
                value = ''
            if not type(value) in self.TYPE_MAP:
                logging.error('Unrecognized value type in record: %s', type(value))
                logging.error('Record: %s', str(record))
                raise TypeError('Unrecognized value type in record: %s', type(value))
            add_cmd = sql.SQL("ALTER TABLE %s ADD COLUMN {field} {type};"
                              % ext.quote_ident(table_name, self.connection)).format(
                field=sql.Identifier(field_name.lower()),
                type=sql.SQL(self.TYPE_MAP[type(value)]))
            try:
                self.exec_sql_command(add_cmd)
                logging.info('Inserting column "%s" with type "%s"', field_name.lower(), self.TYPE_MAP[type(value)])
            # It's okay if the column already exists
            except psycopg2.errors.DuplicateColumn:
                self.connection.rollback()
                pass
            except Exception:
                raise

    ############################
    def _get_table_columns(self, table_name):
        """Get columns (we could probably cache these, checking against the
    existence of self.last_record_read[table_name] to know when we
    need to rebuild."""
        table_name = table_name.lower()
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT * FROM  %s LIMIT 0;" % ext.quote_ident(table_name, self.connection))
            columns = [desc[0] for desc in cursor.description]
        except Exception:
            raise
        finally:
            cursor.close()
        return columns

    ############################
    def _num_rows(self, table_name):
        table_name = table_name.lower()
        query = "SELECT COUNT(1) FROM %s;" % ext.quote_ident(table_name, self.connection)
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            num_rows = next(cursor)[0]
        except Exception:
            raise
        finally:
            cursor.close()
        return num_rows

    ############################
    def _fetch_and_parse_records(self, table_name, field_list, condition_clause=None, data=[]):
        """Fetch records, give DB query, and parse into DASRecords."""
        data_id = table_name.lower()

        # If they haven't given us any fields, retrieve everything
        if not field_list:
            f = self._get_table_columns(table_name)
            query = sql.SQL("SELECT * FROM %s"
                            % ext.quote_ident(data_id, self.connection))
        else:
            f = ['id', 'timestamp'] + [x.lower() for x in field_list]
            query = sql.SQL("SELECT {fields} FROM %s"
                        % ext.quote_ident(data_id, self.connection)).format(
                        fields=sql.SQL(', ').join(map(sql.Identifier, f)))

        if condition_clause:
            query = sql.SQL(' ').join([query, condition_clause])

        cursor = self.connection.cursor()
        try:
            cursor.execute(query, data)
            results = []
            for values in cursor:
                logging.info('value: %s', values)
                r = dict(zip(f, values))
                logging.info('r: %s', r)
                id = r.pop('id')
                self.next_id[table_name] = id + 1

                timestamp = r.pop('timestamp')
                results.append(DASRecord(data_id=data_id, message_type=None,
                                         timestamp=timestamp, fields=r))
        except Exception:
            raise
        finally:
            cursor.close()
        return results

    ############################
    def read(self, table_name, field_list=None, start=None):
        """Read the next record from table. If start is specified, reset read
    to start at that position."""

        if start is None:
            if not table_name in self.next_id:
                self.next_id[table_name] = 1
            start = self.next_id[table_name]

        condition_clause = sql.SQL('WHERE (id = %s)')

        data = [start]

        result = self._fetch_and_parse_records(table_name, field_list, condition_clause, data)

        if not result:
            return None
        return result[0]

    ############################
    def seek(self, table_name, offset=0, origin='current'):
        """Behavior is intended to mimic file seek() behavior but with
    respect to records: 'offset' means number of records, and origin
    is either 'start', 'current' or 'end'."""
        table_name = table_name.lower()
        if not table_name in self.next_id:
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
    def read_range(self, table_name, field_list=None, start=None, stop=None):
        """Read one or more records from table (start and stop inclusive).
    If start is not specified, begin reading at the next not-yet-read record.
    If stops is not specified, read as many records as are available."""

        table_name = table_name.lower()
        if start is None:
            if not table_name in self.next_id:
                self.next_id[table_name] = 1
            start = self.next_id[table_name]

        condition_clause = sql.SQL('WHERE id >= %s')
        data = [start]

        if stop is not None:
            condition_clause = sql.SQL(' ').join([condition_clause, sql.SQL('AND id <= %s')])
            data.append(stop)

        return self._fetch_and_parse_records(table_name, field_list, condition_clause, data)

    ############################
    def read_time_range(self, table_name, field_list=None,
                        start_time=None, stop_time=None):
        """Read one or more records from table (start_time and stop_time inclusive).
    If start_time is not specified, begin reading at the earliest record.
    If stop_time is not specified, read to the most recent.
    NOTE: Timescaledb returns time ranges with the oldest first"""
        if not isinstance(start_time, datetime):
            start_time = datetime.fromtimestamp(start_time, tz=timezone.utc)
        if not isinstance(stop_time, datetime):
            stop_time = datetime.fromtimestamp(stop_time, tz=timezone.utc)

        table_name = table_name.lower()
        if start_time is not None and stop_time is not None:
            condition_clause = sql.SQL("WHERE timestamp >= %s AND timestamp <= %s")
            data = [start_time, stop_time]
        elif start_time is not None:
            condition_clause = sql.SQL("WHERE timestamp >= %s")
            data = [start_time]
        elif stop_time is not None:
            condition_clause = sql.SQL("WHERE timestamp <= %s")
            data = [stop_time]
        else:
            condition_clause = None
            data = []

        return self._fetch_and_parse_records(table_name, field_list, condition_clause, data)

    ############################
    def delete_table(self, table_name):
        table_name = table_name.lower()
        delete_cmd = sql.SQL('DROP TABLE %s;' % ext.quote_ident(table_name, self.connection))
        logging.info('Dropping table with command: %s', delete_cmd)

        self.exec_sql_command(delete_cmd)

        # Clear out our recollection of how far into the table we've read
        if table_name in self.next_id:
            del self.next_id[table_name]

        # Delete any references to that table from the file name mapping
        delete_refs = sql.SQL("DELETE FROM %s WHERE table_name = %%s" % \
                      ext.quote_ident(self.FIELD_NAME_MAPPING_TABLE, self.connection))
        data = [table_name]
        logging.info('Removing table references with command: %s', delete_refs)
        try:
            self.exec_sql_command(delete_refs, data)
        except psycopg2.errors.UndefinedColumn:
            self.connection.rollback()
            pass

    ############################
    def close(self):
        self.connection.close()
