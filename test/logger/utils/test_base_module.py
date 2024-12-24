#!/usr/bin/env python3
import logging
import sys
import unittest

from typing import Union

sys.path.append('.')
from logger.transforms.transform import Transform  # noqa: E402
from logger.utils.base_module import get_method_type_hints  # noqa: E402


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


############################
class TestTransform(unittest.TestCase):
    ############################
    def test_type_hints(self):
        class ChildTransform(Transform):
            def __init__(self, quiet=False):
                super().__init__(quiet=quiet)  # types of records we can handle

            def transform(self, record: Union[int, str, float]):
                if not self.can_process_record(record):  # inherited from Transform()
                    return self.digest_record(record)  # inherited from Transform()
                return str(record) + '+'

        t = ChildTransform()
        self.assertFalse(t.can_process_record([1, 2, 3]))
        self.assertFalse(t.can_process_record({1: 2, 2: 3}))
        self.assertTrue(t.can_process_record('str'))

        # Hand transform something it can't handle. Should warn us
        with self.assertLogs(logging.getLogger(), logging.WARNING):
            result = t.transform({1: 2, 2: 3})
            self.assertEqual(result, None)

        result = t.transform(5)
        self.assertEqual(result, '5+')

        result = t.transform(['a', 'b', 3.14])
        self.assertEqual(result, ['a+', 'b+', '3.14+'])

        result = t.transform(['a', 'b', None, 3.14])
        self.assertEqual(result, ['a+', 'b+', '3.14+'])

        # Should complain, but parse everything else in list
        with self.assertLogs(logging.getLogger(), logging.WARNING):
            result = t.transform(['a', {1: 2, 2: 3}, 'b', None, 3.14])
            self.assertEqual(result, ['a+', 'b+', '3.14+'])

        # Now tell it to not complain
        t = ChildTransform(quiet=True)
        # Hand transform something it can't handle. Should remain quiet, but
        # return None
        result = t.transform({1: 2, 2: 3})
        self.assertEqual(result, None)

        result = t.transform(['a', {1: 2, 2: 3}, 'b', None, 3.14])
        self.assertEqual(result, ['a+', 'b+', '3.14+'])

    ############################
    def test_no_type_hints(self):

        class ChildTransform(Transform):
            def __init__(self, quiet=False):
                super().__init__(quiet=quiet)  # types of records we can handle

            def transform(self, record):
                if not self.can_process_record(record):  # inherited from Transform()
                    return self.digest_record(record)  # inherited from Transform()
                return str(record) + '+'

        t = ChildTransform()
        self.assertTrue(t.can_process_record('str'))
        self.assertTrue(t.can_process_record({1: 2, 3: 4}))
        self.assertFalse(t.can_process_record([1, 2, 3]))
        self.assertFalse(t.can_process_record(None))

        result = t.transform({1: 2, 2: 3})
        self.assertEqual(result, '{1: 2, 2: 3}+')

        result = t.transform(5)
        self.assertEqual(result, '5+')

        result = t.transform(['a', 'b', 3.14])
        self.assertEqual(result, ['a+', 'b+', '3.14+'])

        result = t.transform(['a', 'b', None, 3.14])
        self.assertEqual(result, ['a+', 'b+', '3.14+'])


if __name__ == '__main__':
    unittest.main()
