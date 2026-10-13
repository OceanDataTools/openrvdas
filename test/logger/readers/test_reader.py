#!/usr/bin/env python3

import unittest
import time

from logger.readers.reader import Reader
from logger.writers.writer import Writer

class MockReader(Reader):
    def __init__(self, records, **kwargs):
        super().__init__(**kwargs)
        self.records = records
        self.index = 0

    def read(self):
        if self.index < len(self.records):
            record = self.records[self.index]
            self.index += 1
            return record
        return None

class MockWriter(Writer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.records = []

    def write(self, record):
        self.records.append(record)

class TestReaderMirror(unittest.TestCase):
    def test_reader_mirror(self):
        records = ['rec1', 'rec2', 'rec3']
        writer = MockWriter()
        reader = MockReader(records=records, mirror_to=writer)

        read_records = []
        while True:
            rec = reader.read()
            if rec is None:
                break
            read_records.append(rec)
        
        self.assertEqual(read_records, records)
        
        # Wait for thread to empty queue
        time.sleep(0.1)
        
        self.assertEqual(writer.records, records)

    def test_reader_mirror_read_with_args(self):
        """A read() that takes optional arguments should still be mirrored."""
        class SizedReader(MockReader):
            def read(self, size=None):
                record = super().read()
                if record is not None and size is not None:
                    record = record[:size]
                return record

        writer = MockWriter()
        reader = SizedReader(records=['rec1', 'rec2', 'rec3'], mirror_to=writer)

        self.assertEqual(reader.read(), 'rec1')
        self.assertEqual(reader.read(2), 're')
        self.assertEqual(reader.read(size=3), 'rec')

        # Wait for thread to empty queue
        time.sleep(0.1)

        self.assertEqual(writer.records, ['rec1', 're', 'rec'])

    def test_reader_mirror_invalid_type(self):
        with self.assertRaisesRegex(TypeError, "mirror_to must be a Writer"):
            MockReader(records=[], mirror_to="not a writer")

if __name__ == '__main__':
    unittest.main()
