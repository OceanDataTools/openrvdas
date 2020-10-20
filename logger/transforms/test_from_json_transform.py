#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.from_json_transform import FromJSONTransform  # noqa: E402
from logger.transforms.to_json_transform import ToJSONTransform  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402

sample_dict = {
    'field1': 'value1',
    'field2': 'value2',
    'field3': 'value3',
}

to_str = '{"field1": "value1", "field2": "value2", "field3": "value3"}'

pretty_str = """{
    "field1": "value1",
    "field2": "value2",
    "field3": "value3"
}"""


class TestFromJSONTransform(unittest.TestCase):

    ############################
    def test_both_ways(self):
        to_trans = ToJSONTransform()
        from_trans = FromJSONTransform()

        result = from_trans.transform(to_trans.transform(sample_dict))
        self.assertDictEqual(sample_dict, result)

    ############################
    def test_to(self):
        to_trans = ToJSONTransform()
        self.assertEqual(to_trans.transform(sample_dict), to_str)

    ############################
    def test_to_pretty(self):
        to_trans = ToJSONTransform(pretty=True)
        self.assertEqual(to_trans.transform(sample_dict), pretty_str)

    ############################

    def test_from(self):
        from_trans = FromJSONTransform()
        result = from_trans.transform(pretty_str)
        self.assertDictEqual(sample_dict, result)

    ############################
    def test_das_record_from(self):
        from_trans = FromJSONTransform(das_record=True)
        result = from_trans.transform(pretty_str)
        self.assertEqual(type(result), DASRecord)
        self.assertDictEqual(sample_dict, result.fields)


################################################################################
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
