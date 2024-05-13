#!/usr/bin/env python3

# flake8: noqa E502  - ignore long lines

import logging
import random
import sys
import unittest

sys.path.append('.')
from logger.utils.nmea_parser import NMEAParser  # noqa: E402

try:
    from database.settings import MONGO_ENABLED
    from database.mongo_record_connector import MongoRecordConnector
except ModuleNotFoundError:
    MONGO_ENABLED = False

SAMPLE_DATA = [
    's330 2017-11-04T05:12:19.479303Z $INZDA,000000.17,07,08,2014,,*78',
    's330 2017-11-04T05:12:19.729748Z $INGGA,000000.16,3934.831698,S,03727.695242,W,1,12,0.7,0.82,M,-3.04,M,,*6F',
    's330 2017-11-04T05:12:19.984911Z $INVTG,227.19,T,245.64,M,10.8,N,20.0,K,A*36',
    's330 2017-11-04T05:12:20.240177Z $INRMC,000000.16,A,3934.831698,S,03727.695242,W,10.8,227.19,070814,18.5,W,A*00',
    's330 2017-11-04T05:12:20.495430Z $INHDT,235.18,T*18',
    's330 2017-11-04T05:12:20.748665Z $PSXN,20,1,0,0,0*3A',
    's330 2017-11-04T05:12:21.000716Z $PSXN,22,-0.05,-0.68*32',
    's330 2017-11-04T05:12:21.256010Z $PSXN,23,-2.82,1.00,235.18,-1.66*3D',
]


class TestDatabase(unittest.TestCase):
    ############################
    @unittest.skipUnless(MONGO_ENABLED, 'Mongo not installed; tests of Mongo '
                         'functionality will not be run.')
    def test_mongo_connector(self):
        parser = NMEAParser()
        try:
            db = MongoRecordConnector(database='test', host='localhost',
                                      user='test', password='test')
        except Exception as e:
            self.assertTrue(False, 'Unable to create database connection. Have you '
                            'set up the appropriate setup script in database/setup?')

        test_num = random.randint(0, 100000)
        records = [parser.parse_record(s) for s in SAMPLE_DATA]
        for i in range(len(records)):
            records[i].data_id = '%d_%s' % (test_num, records[i].data_id)
            table_name = db.table_name_from_record(records[i])
            logging.info('Deleting table %s', table_name)
            if db.table_exists(table_name):
                db.delete_table(table_name)
            self.assertFalse(db.table_exists(table_name))

        # Delete the mapping table so that we can test its automatic creation
        if db.table_exists(db.FIELD_NAME_MAPPING_TABLE):
            try:
                db.delete_table(db.FIELD_NAME_MAPPING_TABLE)
            except:
                pass

        for record in records:
            table_name = db.table_name_from_record(record)

            self.assertFalse(db.table_exists(table_name))
            db.create_table_from_record(record)
            self.assertTrue(db.table_exists(table_name))

            db.write_record(record)
            result = db.read(table_name)
            self.assertEqual(record, result)

            # Some fields can come from more than one record, and we only
            # map to the first such record/table_name
            # for field in record.fields:
            #  self.assertEqual(table_name, db.table_name_from_field(field))

            # Make sure we don't get anything when we try a second read
            self.assertFalse(db.read(table_name))

        for record in records:
            table_name = db.table_name_from_record(record)
            db.write_record(record)
            results = db.read_range(table_name, start=0)
            logging.debug('Read records: %s', [str(r) for r in results])
            self.assertEqual(len(results), 2)

        table_name = db.table_name_from_record(records[0])

        db.seek(table_name, 0, 'start')
        self.assertEqual(db.read(table_name), records[0])
        self.assertEqual(db.read(table_name), records[0])
        self.assertEqual(db.read(table_name), None)
        db.seek(table_name, -2, 'current')
        self.assertEqual(db.read(table_name), records[0])
        self.assertEqual(db.read(table_name), records[0])
        self.assertEqual(db.read(table_name), None)
        db.seek(table_name, -1, 'end')
        self.assertEqual(db.read(table_name), records[0])
        self.assertEqual(db.read(table_name), None)

        # Finally, clean up
        for record in records:
            table_name = db.table_name_from_record(record)
            db.delete_table(table_name)
            self.assertFalse(db.table_exists(table_name))

        db.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
