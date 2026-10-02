#!/usr/bin/env python3

import logging
import unittest

from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.modify_value_transform import ModifyValueTransform  # noqa: E402


class TestModifyValueTransform(unittest.TestCase):

    ###############
    def test_basic(self):
        transform = ModifyValueTransform(
            fields={
                'f1': {'mult_factor': 2, 'add_factor': 1},
                'f2': {'mult_factor': 2},
                'f3': {'add_factor': 1},
                'f4': {'mult_factor': 2, 'output_name': 'f4_output'},
                'f5': {'mult_factor': 2, 'output_name': 'f5_output', 'delete_original': True}
            }
        )
        record = DASRecord(timestamp=1, fields={'f1': 5, 'f2': 5, 'f3': 5, 'f4': 5,
                                                'f5': 5, 'f6': 5})
        result = transform.transform(record)
        self.assertEqual(result.as_json(),
                         '{"data_id": null, "message_type": null, "timestamp": 1, "fields": '
                         '{"f1": 11.0, "f2": 10.0, "f3": 6.0, "f4": 5, "f6": 5, '
                         '"f4_output": 10.0, "f5_output": 10.0}, "metadata": {}}')

        transform = ModifyValueTransform(
            fields={'f1': {'mult_factor': 2, 'add_factor': 1}},
            delete_unmatched=True
        )
        record = DASRecord(timestamp=1, fields={'f1': 5, 'f2': 5, 'f3': 5, 'f4': 5, 'f5': 5})
        result = transform.transform(record)
        self.assertEqual(result.as_json(),
                         '{"data_id": null, "message_type": null, "timestamp": 1, "fields": '
                         '{"f1": 11.0}, "metadata": {}}')

    ###############
    # Issue #644: DASRecord's first positional arg is json_str, not fields, so
    # passing a dict positionally handed it to json.loads() and every dict
    # record raised - even though the type hint advertises dict support and
    # can_process_record() returns True for one.
    def test_dict_record(self):
        transform = ModifyValueTransform(fields={'f1': {'mult_factor': 2, 'add_factor': 1}})

        # can_process_record() and transform() must agree about dicts
        self.assertTrue(transform.can_process_record({'f1': 5}))

        # A bare field dict comes back as a bare field dict
        result = transform.transform({'f1': 5, 'f2': 7})
        self.assertEqual(result, {'f1': 11.0, 'f2': 7})

        # ...and a dict carrying a 'fields' sub-dict keeps its envelope
        result = transform.transform({'data_id': 'd1', 'timestamp': 1,
                                      'fields': {'f1': 5, 'f2': 7}})
        self.assertEqual(result['fields'], {'f1': 11.0, 'f2': 7})
        self.assertEqual(result['timestamp'], 1)
        self.assertEqual(result['data_id'], 'd1')

        # A DASRecord still comes back as a DASRecord
        result = transform.transform(DASRecord(timestamp=1, fields={'f1': 5}))
        self.assertEqual(result.fields, {'f1': 11.0})

    ###############
    # Issue #644: float(None) raises TypeError, not ValueError, so a None
    # field value escaped the handler that is meant to skip unconvertible
    # values and propagated out of the transform.
    def test_none_value(self):
        transform = ModifyValueTransform(fields={'f1': {'mult_factor': 2, 'add_factor': 1}})

        # None is skipped and left alone, like any other unconvertible value
        result = transform.transform(DASRecord(timestamp=1, fields={'f1': None, 'f2': 7}))
        self.assertEqual(result.fields, {'f1': None, 'f2': 7})

        # ...and the same by way of a dict, which is how JSON null arrives
        self.assertEqual(transform.transform({'f1': None, 'f2': 7}),
                         {'f1': None, 'f2': 7})

        # A non-numeric string must still be skipped the way it always was
        result = transform.transform(DASRecord(timestamp=1, fields={'f1': 'bad'}))
        self.assertEqual(result.fields, {'f1': 'bad'})

        # Both unconvertible cases should warn, not raise
        with self.assertLogs(logging.getLogger(), logging.WARNING):
            transform.transform(DASRecord(timestamp=1, fields={'f1': None}))
        with self.assertLogs(logging.getLogger(), logging.WARNING):
            transform.transform(DASRecord(timestamp=1, fields={'f1': 'bad'}))

    ###############
    def test_bad_initialization(self):
        with self.assertRaises(ValueError):
            ModifyValueTransform(
                fields={'f1': {'mult_factor': 2, 'add_factor': 1, 'extra_field': 0}})

        with self.assertRaises(ValueError):
            ModifyValueTransform(
                fields={'f1': {'mult_factor': 'f', 'add_factor': 1}})

        with self.assertRaises(ValueError):
            ModifyValueTransform(
                fields={'f1': {'mult_factor': 1, 'add_factor': 'a'}})

    ###############
    def test_warnings(self):
        # Warn if we can't convert a value in the record
        transform = ModifyValueTransform(fields={'f1': {'mult_factor': 2, 'add_factor': 1}})
        with self.assertLogs(logging.getLogger(), logging.WARNING):
            record = DASRecord(fields={'f1': 'a'})
            transform.transform(record)

        # If we're going to overwrite a prexisting value in the record
        transform = ModifyValueTransform(fields={'f1': {'mult_factor': 2, 'output_name': 'f2'}})
        with self.assertLogs(logging.getLogger(), logging.WARNING):
            record = DASRecord(fields={'f1': 2, 'f2': 3})
            transform.transform(record)

        # Now try with "quiet" flag - shouldn't log anything
        transform = ModifyValueTransform(fields={'f1': {'mult_factor': 2, 'add_factor': 1}},
                                         quiet=True)
        record = DASRecord(fields={'f1': 'a'})
        transform.transform(record)

        transform = ModifyValueTransform(fields={'f1': {'mult_factor': 2, 'output_name': 'f2'}},
                                         quiet=True)
        record = DASRecord(fields={'f1': 2, 'f2': 3})
        transform.transform(record)

    ###############
    # test with new metadata, and with pre-existing metadata
    def test_metadata(self):
        transform = ModifyValueTransform(
            fields={'f1': {'mult_factor': 2, 'add_factor': 1, 'metadata': 'f1 metadata'},
                    'f2': {'mult_factor': 2, 'metadata': 'f2 metadata'}},
            metadata_interval=5
        )

        # First record should get metadata, second record shouldn't
        record = DASRecord(timestamp=10, fields={'f1': 5, 'f2': 5})
        result = transform.transform(record)
        self.assertEqual(result.as_json(),
                         '{"data_id": null, "message_type": null, "timestamp": 10, "fields": '
                         '{"f1": 11.0, "f2": 10.0}, '
                         '"metadata": {"f1": "f1 metadata", "f2": "f2 metadata"}}')

        record = DASRecord(timestamp=11, fields={'f1': 5, 'f2': 5})
        result = transform.transform(record)
        self.assertEqual(result.as_json(),
                         '{"data_id": null, "message_type": null, "timestamp": 11, "fields": '
                         '{"f1": 11.0, "f2": 10.0}, "metadata": {}}')

        # Now try with pre-existing metadata. Not time to add new metadata, so just pass
        # along existing in record.
        record = DASRecord(timestamp=12, fields={'f1': 5, 'f2': 5},
                           metadata={'f1': 'old f1 metadata', 'f3': 'f3 metadata'})
        result = transform.transform(record)
        self.assertEqual(result.as_json(),
                         '{"data_id": null, "message_type": null, "timestamp": 12, "fields": '
                         '{"f1": 11.0, "f2": 10.0}, '
                         '"metadata": {"f1": "old f1 metadata", "f3": "f3 metadata"}}')

        # New f1 metadata field should replace old one
        record = DASRecord(timestamp=20, fields={'f1': 5, 'f2': 5},
                           metadata={'f1': 'old f1 metadata', 'f3': 'f3 metadata'})
        result = transform.transform(record)
        self.assertEqual(result.as_json(),
                         '{"data_id": null, "message_type": null, "timestamp": 20, "fields": '
                         '{"f1": 11.0, "f2": 10.0}, '
                         '"metadata": {"f1": "f1 metadata", "f3": "f3 metadata", '
                         '"f2": "f2 metadata"}}')


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
