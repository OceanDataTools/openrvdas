#!/usr/bin/env python3
"""
TBD
"""
import logging
import sys

from os.path import dirname, realpath; sys.path.append(dirname(dirname(realpath(__file__))))
from logger.utils.formats import Python_Record
from logger.utils.das_record import DASRecord

try:
  import psycopg2
  POSTGRES_ENABLED = True
except ImportError:
  POSTGRES_ENABLED = False

################################################################################
class CORIOLIXConnector:
  # Name of table in which we will store mappings from record field
  # names to the tnames of the tables containing those fields.

  def __init__(self, database, host, user, password, tail=False):
    """Interface to CORIOLIXConnector, to be imported by, e.g. DatabaseWriter."""
    if not POSTGRES_ENABLED:
      logging.warning('PostGreSQL not found, so PostGreSQL functionality not available.')
      return

    self.database = database

    try:
      self.connection = psycopg2.connect(database=database, host=host, user=user, password=password)
    except:
      raise RuntimeError('Unable to connect to CORIOLIX database.')

    # What's the next id we're supposed to read? Or if we've been
    # reading by timestamp, what's the last timestamp we've seen?
    self.next_id = 1
    self.last_timestamp = 0

    # self.exec_sql_command('SET AUTOCOMMIT TO ON')
    self.connection.set_session(autocommit=True)

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
    except psycopg2.errors.ProgrammingError as e:
      logging.error('Executing command: "%s", encountered error "%s"',
                    command, str(e))
    except Exception as e:
      logging.error('Other error: "%s", encountered error "%s"',
                    command, str(e))

  ############################
  def table_exists(self, table_name):
    """Does the specified table exist in the database?"""

    # SELECT EXISTS ( SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'anemo_mmast_archive');

    cursor = self.connection.cursor()
    # logging.warning(cursor.mogrify('SELECT EXISTS ( SELECT FROM information_schema.tables WHERE table_schema = \'public\' AND table_name = \'%s\')' % (table_name)))
    cursor.execute('SELECT EXISTS ( SELECT FROM information_schema.tables WHERE table_schema = \'public\' AND table_name = \'%s\')' % (table_name))
    if cursor.fetchone()[0]:
      exists = True
    else:
      exists = False
    return exists

  ############################
  def read(self, table_name, field_list=None, start=None, num_records=1):
    """Read the next record from table. If start is specified, reset read
    to start at that position."""

    if start is None:
      start = self.next_id
    condition = 'id >= %d' % start

    # If they haven't given us any fields, retrieve everything
    if field_list:
      field_conditions = ['field_name=\'%s\'' % f for f in field_list.split(',')]
      condition += ' and (%s)' % ' or '.join(field_conditions)

    condition += ' order by id'

    if num_records is not None:
      condition += ' limit %d' % num_records

    query = 'select * from %s where %s' % (table_name, condition)
    logging.debug('read query: %s', query)
    return self._process_query(query)

  ############################
  def _num_rows(self, table_name):
    query = 'select count(1) from %s' % table_name
    cursor = self.connection.cursor()
    cursor.execute(query)
    num_rows = next(cursor)[0]
    return num_rows

  ############################
  def close(self):
    """Close connection."""
    self.connection.close()
