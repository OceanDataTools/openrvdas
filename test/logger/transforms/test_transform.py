#!/usr/bin/env python3

import logging
import unittest
import time

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

    def test_transform_mirror_only_outermost_call(self):
        """A transform that calls its own transform(), with extra arguments,
        should mirror only what it hands downstream (issue #648)."""
        class MockWriter(Writer):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.records = []

            def write(self, record):
                self.records.append(record)

        class RecursiveTransform(Transform):
            def transform(self, record, suffix='+'):
                if isinstance(record, list):
                    return [self.transform(r, suffix=suffix) for r in record]
                return str(record) + suffix

        writer = MockWriter()
        transform = RecursiveTransform(mirror_to=writer)

        self.assertEqual(transform.transform('a'), 'a+')
        self.assertEqual(transform.transform('b', '-'), 'b-')
        self.assertEqual(transform.transform(['c', 'd'], suffix='!'), ['c!', 'd!'])

        # Wait for thread (assuming mirroring might be asynchronous)
        time.sleep(0.1)

        self.assertEqual(writer.records, ['a+', 'b-', ['c!', 'd!']])

    def test_transform_mirror_invalid_type(self):
        with self.assertRaisesRegex(TypeError, "mirror_to must be a Writer"):
            PrefixTransform(prefix='p', mirror_to="not a writer")


if __name__ == '__main__':
    unittest.main()
