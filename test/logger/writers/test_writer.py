#!/usr/bin/env python3

import logging
import sys
import unittest

sys.path.append('.')
from logger.writers.writer import Writer  # noqa: E402


class TestWriter(unittest.TestCase):
    ############################
    def test_warn_if_deprecated(self):
        class ChildWriter(Writer):
            def __init__(self):
                super().__init__(input_format='foo')

            def write(self, record):
                pass

        with self.assertLogs(logging.getLogger(), logging.WARNING):
            ChildWriter()


if __name__ == '__main__':
    unittest.main()
