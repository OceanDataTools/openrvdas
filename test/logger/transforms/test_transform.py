#!/usr/bin/env python3

import logging
import sys
import unittest
import time

sys.path.append('.')
from logger.transforms.transform import Transform
from logger.transforms.prefix_transform import PrefixTransform
from logger.writers.writer import Writer
  # noqa: E402


############################
class TestTransform(unittest.TestCase):
    ############################
    def test_warn_if_deprecated(self):
        class ChildTransform(Transform):
            def __init__(self):
                super().__init__(input_format='foo')

            def transform(self, record):
                return str(record) + '+'

        with self.assertLogs(logging.getLogger(), logging.WARNING):
            ChildTransform()

    def test_transform_mirror(self):
        class MockWriter(Writer):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.records = []

            def write(self, record):
                self.records.append(record)

        writer = MockWriter()
        transform = PrefixTransform(prefix='prefix: ', sep='', mirror_to=writer)
        
        self.assertEqual(transform.transform('start'), 'prefix: start')
        self.assertEqual(transform.transform('end'), 'prefix: end')
        
        # Wait for thread (assuming mirroring might be asynchronous)
        time.sleep(0.1)
        
        self.assertEqual(writer.records, ['prefix: start', 'prefix: end'])

    def test_transform_mirror_invalid_type(self):
        with self.assertRaisesRegex(TypeError, "mirror_to must be a Writer"):
            PrefixTransform(prefix='p', mirror_to="not a writer")


if __name__ == '__main__':
    unittest.main()
