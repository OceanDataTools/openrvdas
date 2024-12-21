#!/usr/bin/env python3
import sys
import unittest

sys.path.append('.')
from logger.utils.type_checking import get_method_type_hints  # noqa: E402


class TestMethodTypes(unittest.TestCase):

    def test_can_accept(self):
        class MyClass:
            def method1(self, record: int | float) -> str:
                return 'str'

            def method2(self, record: int | float):
                return 'str'

            def method3(self, record: int) -> str:
                return 'str'

            def method4(self, record):
                return 'str'

        self.assertDictEqual(get_method_type_hints(MyClass.method1),
                             {'return': tuple([str]), 'record': tuple([int, float])})
        self.assertDictEqual(get_method_type_hints(MyClass.method2),
                             {'record': tuple([int, float])})
        self.assertDictEqual(get_method_type_hints(MyClass.method3),
                             {'return': tuple([str]), 'record': tuple([int])})
        self.assertDictEqual(get_method_type_hints(MyClass.method4), {})


if __name__ == '__main__':
    unittest.main()
