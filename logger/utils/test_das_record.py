#!/usr/bin/env python3

import json
import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.utils import timestamp  # noqa: E402

JSON_IN = """{
  "timestamp": 1510265335,
  "data_id": "gyr1",
  "message_type": "",
  "fields": {
    "GYR_Heading": 314.15,
    "GYR_Acc": 0.11
  },
  "metadata": {
    "calibration_date": "2017-01-13",
    "status": "good",
    "sending_host": "betelgeuse"
  }
}
"""

################################################################################


class TestDASRecord(unittest.TestCase):

    def test_basic(self):
        dr = DASRecord()
        self.assertAlmostEqual(dr.timestamp, timestamp.timestamp(), 2)
        self.assertAlmostEqual(dr.timestamp, timestamp.timestamp(), 2)
        self.assertEqual(dr.data_id, None)
        self.assertEqual(dr.fields, {})
        self.assertEqual(dr.metadata, {})

    def test_json(self):
        dr = DASRecord(json=JSON_IN)
        self.assertEqual(dr.timestamp, 1510265335)
        self.assertEqual(dr.data_id, 'gyr1')
        self.assertEqual(dr.fields['GYR_Heading'], 314.15)
        self.assertEqual(dr.metadata['status'], 'good')

        self.assertDictEqual(json.loads(dr.as_json()), json.loads(JSON_IN))


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

    # logging.getLogger().setLevel(logging.DEBUG)
    unittest.main(warnings='ignore')
