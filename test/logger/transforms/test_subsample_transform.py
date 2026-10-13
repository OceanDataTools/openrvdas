#!/usr/bin/env python3

import logging
import time
import unittest
from unittest import mock

from logger.transforms.subsample_transform import SubsampleTransform  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402


class MockWriter(Writer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.records = []

    def write(self, record):
        self.records.append(record)


class TestSubsampleTransform(unittest.TestCase):

    ############################
    # When given a list, the mirror_to writer should get the list that is
    # handed downstream, and not also each of its elements (issue #648).
    def test_list_with_mirror(self):
        field_spec = {'a': {'output': 'avg_a',
                            'subsample': {'type': 'boxcar_average',
                                          'window': 10, 'interval': 1}}}
        writer = MockWriter()
        with self.assertLogs(logging.getLogger(), logging.WARNING):  # deprecated
            transform = SubsampleTransform(field_spec=field_spec, mirror_to=writer)

        now = time.time()
        records = [{'timestamp': now - 2, 'fields': {'a': 1}},
                   {'timestamp': now - 1, 'fields': {'a': 3}}]

        # We're testing the mirroring, not the subsampling, so have every
        # record produce a result.
        with mock.patch('logger.transforms.subsample_transform.subsample',
                        return_value=[(now, 2.0)]):
            result = transform.transform(records)

        self.assertEqual(len(result), 2)
        self.assertNotIn(None, result)

        # Mirroring is asynchronous; give the thread a moment
        time.sleep(0.1)

        self.assertEqual(writer.records, [result])


if __name__ == '__main__':
    unittest.main()
