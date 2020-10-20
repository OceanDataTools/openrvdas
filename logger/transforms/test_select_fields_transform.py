#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.select_fields_transform import SelectFieldsTransform  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402


class TestSelectFieldTransform(unittest.TestCase):

    ############################
    def test_keep(self):
        t = SelectFieldsTransform(keep=['a', 'b'])

        # Check for field dict
        self.assertDictEqual(t.transform({'fields': {'a': 1, 'b': 2, 'c': 3}}),
                             {'fields': {'a': 1, 'b': 2}})
        self.assertDictEqual(t.transform({'fields': {'b': 2, 'c': 3}}),
                             {'fields': {'b': 2}})
        self.assertEqual(t.transform({'fields': {'d': 1, 'e': 2, 'c': 3}}), None)

        # Repeat for DASRecord
        dt = t.transform(DASRecord(fields={'a': 1, 'b': 2, 'c': 3}))
        self.assertDictEqual(dt.fields, {'a': 1, 'b': 2})

        dt = t.transform(DASRecord(fields={'b': 2, 'c': 3}))
        self.assertDictEqual(dt.fields, {'b': 2})

        dt = t.transform(DASRecord(fields={'d': 1, 'e': 2, 'c': 3}))
        self.assertEqual(dt, None)

        # Repeat for top-level dict
        self.assertDictEqual(t.transform({'a': 1, 'b': 2, 'c': 3}), {'a': 1, 'b': 2})
        self.assertDictEqual(t.transform({'b': 2, 'c': 3}), {'b': 2})
        self.assertEqual(t.transform({'d': 1, 'e': 2, 'c': 3}), None)

        # Verify that transform doesn't modify original record
        fd = {'fields': {'a': 1, 'b': 2, 'c': 3}}
        self.assertDictEqual(t.transform(fd), {'fields': {'a': 1, 'b': 2}})
        self.assertDictEqual(fd, {'fields': {'a': 1, 'b': 2, 'c': 3}})

    ############################
    def test_delete(self):
        t = SelectFieldsTransform(delete=['a', 'b'])

        self.assertDictEqual(t.transform({'fields': {'a': 1, 'b': 2, 'c': 3}}),
                             {'fields': {'c': 3}})
        self.assertDictEqual(t.transform({'fields': {'b': 2, 'c': 3}}),
                             {'fields': {'c': 3}})
        self.assertDictEqual(t.transform({'fields': {'d': 1, 'e': 2, 'c': 3}}),
                             {'fields': {'d': 1, 'e': 2, 'c': 3}})

        # Repeat for DASRecord
        dt = t.transform(DASRecord(fields={'a': 1, 'b': 2, 'c': 3}))
        self.assertDictEqual(dt.fields, {'c': 3})

        dt = t.transform(DASRecord(fields={'b': 2, 'c': 3}))
        self.assertDictEqual(dt.fields, {'c': 3})

        dt = t.transform(DASRecord(fields={'d': 1, 'e': 2, 'c': 3}))
        self.assertDictEqual(dt.fields, {'d': 1, 'e': 2, 'c': 3})

        # Repeat for top-level dict
        self.assertDictEqual(t.transform({'a': 1, 'b': 2, 'c': 3}), {'c': 3})
        self.assertDictEqual(t.transform({'b': 2, 'c': 3}), {'c': 3})
        self.assertDictEqual(t.transform({'d': 1, 'e': 2, 'c': 3}),
                             {'d': 1, 'e': 2, 'c': 3})


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
