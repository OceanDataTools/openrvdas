#!/usr/bin/env python3

import sys
import unittest
import threading
import queue
import time
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))
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

    def test_reader_mirror_invalid_type(self):
        with self.assertRaisesRegex(TypeError, "mirror_to must be a Writer"):
            MockReader(records=[], mirror_to="not a writer")

if __name__ == '__main__':
    unittest.main()
