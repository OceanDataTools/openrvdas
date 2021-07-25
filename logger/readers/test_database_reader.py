#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.record_parser import RecordParser  # noqa: E402
from logger.writers.database_writer import DatabaseWriter  # noqa: E402
from logger.readers.database_reader import DatabaseReader  # noqa: E402
from database.settings import DATABASE_ENABLED  # noqa: E402

SAMPLE_DATA = [
    's330 2017-11-04T06:54:07.173130Z $INZDA,002033.17,07,08,2014,,*7A',
    's330 2017-11-04T06:54:09.210395Z $INZDA,002034.17,07,08,2014,,*7D',
    's330 2017-11-04T06:54:11.248784Z $INZDA,002035.17,07,08,2014,,*7C',
    's330 2017-11-04T06:54:13.290817Z $INZDA,002036.17,07,08,2014,,*7F',
    's330 2017-11-04T06:54:15.328116Z $INZDA,002037.17,07,08,2014,,*7E',
    's330 2017-11-04T06:54:17.371220Z $INZDA,002038.17,07,08,2014,,*71',
    's330 2017-11-04T06:54:19.408518Z $INZDA,002039.17,07,08,2014,,*70',
]

SAMPLE_RESULTS = [
    {'S330GPSTime': [(1509778447.17313, 2033.17)]},
    {'S330GPSDay': [(1509778447.17313, 7)]},
    {'S330GPSMonth': [(1509778447.17313, 8)]},
    {'S330GPSYear': [(1509778447.17313, 2014)]},

    {'S330GPSTime': [(1509778449.210395, 2034.17)]},
    {'S330GPSDay': [(1509778449.210395, 7)]},
    {'S330GPSMonth': [(1509778449.210395, 8)]},
    {'S330GPSYear': [(1509778449.210395, 2014)]},

    {'S330GPSTime': [(1509778451.248784, 2035.17)]},
    {'S330GPSDay': [(1509778451.248784, 7)]},
    {'S330GPSMonth': [(1509778451.248784, 8)]},
    {'S330GPSYear': [(1509778451.248784, 2014)]},

    {'S330GPSTime': [(1509778453.290817, 2036.17)]},
    {'S330GPSDay': [(1509778453.290817, 7)]},
    {'S330GPSMonth': [(1509778453.290817, 8)]},
    {'S330GPSYear': [(1509778453.290817, 2014)]},
    {'S330GPSTime': [(1509778455.328116, 2037.17)]},
    {'S330GPSDay': [(1509778455.328116, 7)]},
    {'S330GPSMonth': [(1509778455.328116, 8)]},
    {'S330GPSYear': [(1509778455.328116, 2014)]},
    {'S330GPSTime': [(1509778457.37122, 2038.17)]},
    {'S330GPSDay': [(1509778457.37122, 7)]},
    {'S330GPSMonth': [(1509778457.37122, 8)]},
    {'S330GPSYear': [(1509778457.37122, 2014)]},
    {'S330GPSTime': [(1509778459.408518, 2039.17)]},
    {'S330GPSDay': [(1509778459.408518, 7)]},
    {'S330GPSMonth': [(1509778459.408518, 8)]},
    {'S330GPSYear': [(1509778459.408518, 2014)]},
    {'S330GPSTime': [(1509778447.17313, 2033.17)]},
    {'S330GPSDay': [(1509778447.17313, 7)]},
    {'S330GPSMonth': [(1509778447.17313, 8)]},
    {'S330GPSYear': [(1509778447.17313, 2014)]}
]


##############################################################################
class TestDatabaseReader(unittest.TestCase):

    ############################
    @unittest.skipUnless(DATABASE_ENABLED, 'Skipping test of DatabaseReader; '
                         'Database not configured in database/settings.py.')
    def test_read(self):
        # Create records using synthetic, randomized data id and write to db
        parser = RecordParser(definition_path='local/usap/nbp/devices/nbp_devices.yaml',
                              return_das_record=True)
        writer = DatabaseWriter(database='test', host='localhost',
                                user='test', password='test')
        writer.db.exec_sql_command('truncate table data')

        reader = DatabaseReader(database='test', host='localhost',
                                user='test', password='test')

        # Write to database, automatically creating table
        records = [parser.parse_record(s) for s in SAMPLE_DATA]
        index = 0
        for record in records:
            logging.debug('Writing record "%s"', str(record))
            writer.write(record)

            result = True
            while result:
                result = writer.db.read()
                logging.info('Read %d: %s', index, result)
                if result:
                    self.assertEqual(result, SAMPLE_RESULTS[index])
                    index += 1

        # Test range: read a range that should include 3 records
        results = reader.read_range(start=2, stop=5)
        self.assertEqual(results, {'S330GPSDay': [(1509778447.17313, 7)],
                                   'S330GPSMonth': [(1509778447.17313, 8)],
                                   'S330GPSYear': [(1509778447.17313, 2014)]})

        # Next record should be one after that
        result = reader.read()
        self.assertEqual(result, {'S330GPSTime': [(1509778449.210395, 2034.17)]})

        # Test time_range: read a range that should include 3 records
        results = reader.read_time_range(start_time=1509778449.210395,
                                         stop_time=1509778453.290818)
        self.assertEqual(results, {'S330GPSTime': [(1509778451.248784, 2035.17),
                                                   (1509778453.290817, 2036.17)],
                                   'S330GPSDay': [(1509778451.248784, 7),
                                                  (1509778453.290817, 7)],
                                   'S330GPSMonth': [(1509778451.248784, 8),
                                                    (1509778453.290817, 8)],
                                   'S330GPSYear': [(1509778451.248784, 2014),
                                                   (1509778453.290817, 2014)]})
        # Next record should be one after that
        result = reader.read()
        self.assertEqual(result, {'S330GPSTime': [(1509778455.328116, 2037.17)]})

        writer.db.close()
        reader.db.close()


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
