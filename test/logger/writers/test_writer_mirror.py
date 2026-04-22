#!/usr/bin/env python3

import unittest
import logging


from logger.writers.writer import Writer

class TestWriterMirror(unittest.TestCase):
    def test_writer_ignores_mirror(self):
        class MockWriter(Writer):
            def write(self, record):
                pass
        
        # Verify it warns
        with self.assertLogs(logging.getLogger(), logging.WARNING) as cm:
            writer = MockWriter(mirror_to=MockWriter())
        
        self.assertTrue(any('passed "mirror_to" argument' in o for o in cm.output))
        
        # Verify mirror_to is None
        self.assertIsNone(writer.mirror_to)

if __name__ == '__main__':
    unittest.main()
