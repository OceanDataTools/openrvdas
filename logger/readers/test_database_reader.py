#!/usr/bin/env python3

import logging
import random
import sys
import unittest
import warnings

sys.path.append('.')
from database.settings import DATABASE_ENABLED

from logger.utils.das_record import DASRecord
from logger.readers.database_reader import DatabaseReader, DatabaseFieldReader
from logger.writers.database_writer import DatabaseWriter
from logger.utils.nmea_parser import NMEAParser

SAMPLE_DATA = [
  's330 2017-11-04:06:54:07.173130 $INZDA,002033.17,07,08,2014,,*7A',
  's330 2017-11-04:06:54:09.210395 $INZDA,002034.17,07,08,2014,,*7D',
  's330 2017-11-04:06:54:11.248784 $INZDA,002035.17,07,08,2014,,*7C',
  's330 2017-11-04:06:54:13.290817 $INZDA,002036.17,07,08,2014,,*7F',
  's330 2017-11-04:06:54:15.328116 $INZDA,002037.17,07,08,2014,,*7E',
  's330 2017-11-04:06:54:17.371220 $INZDA,002038.17,07,08,2014,,*71',
  's330 2017-11-04:06:54:19.408518 $INZDA,002039.17,07,08,2014,,*70',
]

PSXN_DATA = [
  's330 2017-11-04:05:12:21.256010 $PSXN,23,-2.82,1.00,235.18,-1.66*3D',
  's330 2017-11-04:05:12:23.274388 $PSXN,23,-2.68,-2.25,235.50,-0.88*1D',
  's330 2017-11-04:05:12:25.295830 $PSXN,23,-2.27,-3.37,235.73,0.34*3F',
  's330 2017-11-04:05:12:27.327301 $PSXN,23,-1.66,-1.70,235.52,1.11*3D',
  's330 2017-11-04:05:12:29.347271 $PSXN,23,-1.14,1.03,235.02,0.91*1D',
  's330 2017-11-04:05:12:31.378723 $PSXN,23,-1.09,2.80,234.72,-0.01*3B',
  's330 2017-11-04:05:12:33.410308 $PSXN,23,-1.47,2.72,234.87,-0.88*37'
]

##############################################################################
class TestDatabaseReader(unittest.TestCase):

  ############################
  @unittest.skipUnless(DATABASE_ENABLED, 'Skipping test of DatabaseReader; '
                       'Database not configured in database/settings.py.')
  def test_read(self):
    # Create records using synthetic, randomized data id and write to db
    test_num = random.randint(0,100000)
    data_id = '%d_s330' % test_num
    message_type = '$INZDA'
    parser = NMEAParser()
    writer = DatabaseWriter(database='test', host='localhost',
                            user='test', password='test',
                            create_if_missing=True)

    reader = DatabaseReader(database='test', host='localhost',
                            user='test', password='test',
                            data_id=data_id, message_type='$INZDA')

    table_name = writer._table_name_from_record(DASRecord(data_id=data_id,
                                                message_type=message_type))
    logging.info('Deleting table %s', table_name)
    if writer._table_exists(table_name):
      writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))
      
    # Write to database, automatically creating table
    records = [parser.parse_record(s) for s in SAMPLE_DATA]
    for i in range(len(records)):
      records[i].data_id = data_id
      logging.debug('Writing record "%s"', str(records[i]))
      writer.write(records[i])

    # Read records back
    for i in range(len(records)):
      logging.debug('Reading next record... %d/%d', i, len(records))
      result = reader.read()

      self.assertEqual(result, records[i])

    # Test range: read a range that should include 3 records
    results = reader.read_range(start=2, stop=5)
    self.assertEqual(len(results), 3)
    self.assertEqual(results[0], records[1])
    self.assertEqual(results[1], records[2])
    self.assertEqual(results[2], records[3])
    
    # Next record should be one after that
    result = reader.read()
    self.assertEqual(result, records[4])

    # Test time_range: read a range that should include 3 records
    results = reader.read_time_range(start_time=1509778449.210395,
                                     stop_time=1509778453.290818)
    self.assertEqual(len(results), 3)
    self.assertEqual(results[0], records[1])
    self.assertEqual(results[1], records[2])
    self.assertEqual(results[2], records[3])
    
    # Next record should be one after that
    result = reader.read()
    self.assertEqual(result, records[4])

    writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))

    writer.db.close()
    reader.db.close()

  ############################
  @unittest.skipUnless(DATABASE_ENABLED, 'Skipping test of DatabaseReader; '
                       'Database not configured in database/settings.py.')
  def test_read_range(self):
    # Create records using synthetic, randomized data id and write to db
    test_num = random.randint(0,100000)
    data_id = '%d_s330' % test_num
    message_type = '$INZDA'
    parser = NMEAParser()
    writer = DatabaseWriter(database='test', host='localhost',
                            user='test', password='test',
                            create_if_missing=True)

    reader = DatabaseReader(database='test', host='localhost',
                            user='test', password='test',
                            data_id=data_id, message_type='$INZDA')

    table_name = writer._table_name_from_record(DASRecord(data_id=data_id,
                                                message_type=message_type))
    logging.info('Deleting table %s', table_name)
    if writer._table_exists(table_name):
      writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))
      
    # Write to database, automatically creating table
    records = [parser.parse_record(s) for s in SAMPLE_DATA]
    for i in range(len(records)):
      records[i].data_id = data_id
      logging.debug('Writing record "%s"', str(records[i]))
      writer.write(records[i])


    writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))

    writer.db.close()
    reader.db.close()

  ############################
  @unittest.skipUnless(DATABASE_ENABLED, 'Skipping test of DatabaseReader; '
                       'Database not configured in database/settings.py.')
  def test_read_time_range(self):
    # Create records using synthetic, randomized data id and write to db
    test_num = random.randint(0,100000)
    data_id = '%d_s330' % test_num
    message_type = '$INZDA'
    parser = NMEAParser()
    writer = DatabaseWriter(database='test', host='localhost',
                            user='test', password='test',
                            create_if_missing=True)

    reader = DatabaseReader(database='test', host='localhost',
                            user='test', password='test',
                            data_id=data_id, message_type='$INZDA')

    table_name = writer._table_name_from_record(DASRecord(data_id=data_id,
                                                message_type=message_type))
    logging.info('Deleting table %s', table_name)
    if writer._table_exists(table_name):
      writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))
      
    # Write to database, automatically creating table
    records = [parser.parse_record(s) for s in SAMPLE_DATA]
    for i in range(len(records)):
      records[i].data_id = data_id
      logging.debug('Writing record "%s"', str(records[i]))
      writer.write(records[i])

    # Read a range that should include 3 records
    results = reader.read_time_range(start_time=1509778449.210395,
                                     stop_time=1509778453.290818)
    self.assertEqual(len(results), 3)
    self.assertEqual(results[0], records[1])
    self.assertEqual(results[1], records[2])
    self.assertEqual(results[2], records[3])
    
    # Next record should be one after that
    result = reader.read()
    self.assertEqual(result, records[4])

    writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))

    writer.db.close()
    reader.db.close()

##############################################################################
class TestDatabaseFieldReader(unittest.TestCase):

  ############################
  @unittest.skipUnless(DATABASE_ENABLED, 'Skipping test of DatabaseReader; '
                       'Database not configured in database/settings.py.')
  def test_read(self):
    # Create records using synthetic, randomized data id and write to db
    test_num = random.randint(0,100000)
    data_id = '%d_s330' % test_num
    message_type = '$INZDA'
    parser = NMEAParser()
    writer = DatabaseWriter(database='test', host='localhost',
                            user='test', password='test',
                            create_if_missing=True)

    reader = DatabaseFieldReader(fields=['S330GPSTime','S330GPSDay','S330Roll'],
                                 database='test', host='localhost',
                                 user='test', password='test')

    table_name = writer._table_name_from_record(DASRecord(data_id=data_id,
                                                message_type=message_type))
    logging.info('Deleting table %s', table_name)
    if writer._table_exists(table_name):
      writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))

    # Write to database, automatically creating table
    records = [parser.parse_record(s) for s in SAMPLE_DATA]
    for i in range(len(records)):
      records[i].data_id = data_id
      logging.debug('Writing record "%s"', str(records[i]))
      writer.write(records[i])

    # Read records back
    for i in range(len(records)):
      logging.debug('Reading next record... %d/%d', i, len(records))
      result = reader.read()
      logging.debug('Got result: "%s"', result)
      self.assertEqual(len(result), 2)
      self.assertEqual(result['S330GPSTime'][0][0], records[i].timestamp)
      self.assertEqual(result['S330GPSTime'][0][1],
                       records[i].fields['S330GPSTime'])
      self.assertEqual(result['S330GPSDay'][0][0], records[i].timestamp)
      self.assertEqual(result['S330GPSDay'][0][1],
                       records[i].fields['S330GPSDay'])

    # Test time_range: read a range that should include 3 records
    results = reader.read_time_range(start_time=1509778449.210395,
                                     stop_time=1509778453.290818)
    self.assertEqual(len(results['S330GPSTime']), 3)
    self.assertEqual(len(results['S330GPSDay']), 3)
    self.assertEqual(results['S330GPSTime'][0],
                     (records[1].timestamp, records[1].fields['S330GPSTime']))
    self.assertEqual(results['S330GPSTime'][1],
                     (records[2].timestamp, records[2].fields['S330GPSTime']))
    self.assertEqual(results['S330GPSTime'][2],
                     (records[3].timestamp, records[3].fields['S330GPSTime']))

    # Next record should be one after that
    result = reader.read() 
    self.assertEqual(result['S330GPSTime'][0],
                     (records[4].timestamp, records[4].fields['S330GPSTime']))

    writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))

    writer.db.close()
    reader.db.close()

  ############################
  @unittest.skipUnless(DATABASE_ENABLED, 'Skipping test of DatabaseReader; '
                       'Database not configured in database/settings.py.')
  def test_read_range(self):
    # Create records using synthetic, randomized data id and write to db
    test_num = random.randint(0,100000)
    data_id = '%d_s330' % test_num
    message_type = '$INZDA'
    parser = NMEAParser()
    writer = DatabaseWriter(database='test', host='localhost',
                            user='test', password='test',
                            create_if_missing=True)

    reader = DatabaseReader(data_id=data_id, message_type='$INZDA',
                            database='test', host='localhost',
                            user='test', password='test')

    table_name = writer._table_name_from_record(DASRecord(data_id=data_id,
                                                message_type=message_type))
    logging.info('Deleting table %s', table_name)
    if writer._table_exists(table_name):
      writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))
      
    # Write to database, automatically creating table
    records = [parser.parse_record(s) for s in SAMPLE_DATA]
    for i in range(len(records)):
      records[i].data_id = data_id
      logging.debug('Writing record "%s"', str(records[i]))
      writer.write(records[i])


    writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))

    writer.db.close()
    reader.db.close()

  ############################
  @unittest.skipUnless(DATABASE_ENABLED, 'Skipping test of DatabaseReader; '
                       'Database not configured in database/settings.py.')
  def test_read_time_range(self):
    # Create records using synthetic, randomized data id and write to db
    test_num = random.randint(0,100000)
    data_id = '%d_s330' % test_num
    message_type = '$INZDA'
    parser = NMEAParser()
    writer = DatabaseWriter(database='test', host='localhost',
                            user='test', password='test',
                            create_if_missing=True)

    reader = DatabaseReader(data_id=data_id, message_type='$INZDA',
                            database='test', host='localhost',
                            user='test', password='test')

    table_name = writer._table_name_from_record(DASRecord(data_id=data_id,
                                                message_type=message_type))
    logging.info('Deleting table %s', table_name)
    if writer._table_exists(table_name):
      writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))
      
    # Write to database, automatically creating table
    records = [parser.parse_record(s) for s in SAMPLE_DATA]
    for i in range(len(records)):
      records[i].data_id = data_id
      logging.debug('Writing record "%s"', str(records[i]))
      writer.write(records[i])

    # Read a range that should include 3 records
    results = reader.read_time_range(start_time=1509778449.210395,
                                     stop_time=1509778453.290818)
    self.assertEqual(len(results), 3)
    self.assertEqual(results[0], records[1])
    self.assertEqual(results[1], records[2])
    self.assertEqual(results[2], records[3])
    
    # Next record should be one after that
    result = reader.read()
    self.assertEqual(result, records[4])

    writer._delete_table(table_name)
    self.assertFalse(writer._table_exists(table_name))

    writer.db.close()
    reader.db.close()

if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
  
  unittest.main(warnings='ignore')
