#!/usr/bin/env python3

import logging
import sys
import unittest

sys.path.append('.')
from logger.transforms.transform import Transform  # noqa: E402


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


if __name__ == '__main__':
    unittest.main()
