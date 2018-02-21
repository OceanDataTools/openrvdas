#!/usr/bin/env python3

import logging
import random
import sys
import unittest
import warnings

sys.path.append('.')

from logger.utils.das_record import DASRecord
from logger.writers.database_writer import DatabaseWriter
from logger.utils.nmea_parser import NMEAParser

SAMPLE_DATA = [
  's330 2017-11-04:05:12:19.479303 $INZDA,000000.17,07,08,2014,,*78',
  's330 2017-11-04:05:12:19.729748 $INGGA,000000.16,3934.831698,S,03727.695242,W,1,12,0.7,0.82,M,-3.04,M,,*6F',
  's330 2017-11-04:05:12:19.984911 $INVTG,227.19,T,245.64,M,10.8,N,20.0,K,A*36',
  's330 2017-11-04:05:12:20.240177 $INRMC,000000.16,A,3934.831698,S,03727.695242,W,10.8,227.19,070814,18.5,W,A*00',
  's330 2017-11-04:05:12:20.495430 $INHDT,235.18,T*18',
  's330 2017-11-04:05:12:20.748665 $PSXN,20,1,0,0,0*3A',
  's330 2017-11-04:05:12:21.000716 $PSXN,22,-0.05,-0.68*32',
  's330 2017-11-04:05:12:21.256010 $PSXN,23,-2.82,1.00,235.18,-1.66*3D',
]

class TestDatabaseWriter(unittest.TestCase):

  ############################
  def test_create_table(self):
    warnings.filterwarnings("ignore", category=ResourceWarning)

    parser = NMEAParser()
    writer = DatabaseWriter(database='test', host='localhost',
                        user='test', password='test',
                        create_if_missing=True)

    test_num = random.randint(0,100000)
    records = [parser.parse_record(s) for s in SAMPLE_DATA]
    for i in range(len(records)):
      records[i].data_id = '%d_%s' % (test_num, records[i].data_id)
      table_name = writer._table_name(records[i])
      logging.info('Deleting table %s', table_name)
      if writer._table_exists(table_name):
        writer._delete_table(table_name)
      self.assertFalse(writer._table_exists(table_name))

    for record in records:
      table_name = writer._table_name(record)

      self.assertFalse(writer._table_exists(table_name))    
      writer.write(record)
      result = writer.db.read(table_name)
      logging.debug('Read record: %s', str(result))
      
      self.assertTrue(writer._table_exists(table_name))

      writer._delete_table(table_name)
      self.assertFalse(writer._table_exists(table_name))
     
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

