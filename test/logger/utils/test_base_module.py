#!/usr/bin/env python3
import ast
import glob
import logging
import os
import unittest

from typing import Union

from logger.transforms.transform import Transform  # noqa: E402
from logger.utils.base_module import get_method_type_hints  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

# Where we look for Readers and Transforms that might be given a mirror_to.
MODULE_DIRS = ['logger/readers', 'logger/transforms', 'contrib']


def find_self_calls(source):
    """Return a list of (line number, description) for every read() or
    transform() method in the passed source code that calls itself, e.g.
    a transform() that calls self.transform()."""
    found = []
    for cls in ast.walk(ast.parse(source)):
        if not isinstance(cls, ast.ClassDef):
            continue
        for method in cls.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            if method.name not in ('read', 'transform'):
                continue
            for node in ast.walk(method):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == method.name
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == 'self'):
                    found.append((node.lineno,
                                  f'{cls.name}.{method.name}() calls '
                                  f'self.{method.name}()'))
    return sorted(found)


# What we tell the developer if we find a read() or transform() that
# calls itself.
SELF_CALL_MESSAGE = """
Found {count} read()/transform() method(s) that call themselves:

{problems}

WHY THIS IS A PROBLEM

  Any Reader or Transform can be given a "mirror_to" writer, which should
  receive a copy of each record the module hands downstream. BaseModule
  implements this by wrapping the module's public read() or transform()
  method, so *every* call to that method sends its result to the mirror.

  If transform() calls self.transform() to do part of its work (typically
  once for each element of a list), each of those inner calls is mirrored
  too. The mirror then gets every element separately and then the whole
  list again, so a mirrored logfile ends up with duplicate records. The
  same goes for a read() that calls self.read() to skip or retry records:
  records that were never handed downstream end up in the mirror.

HOW TO FIX IT

  Move the work into a private helper method, have the public method call
  the helper, and have the helper call itself rather than the public
  method. Private methods are not wrapped, so nothing extra is mirrored.

  Instead of:

      def transform(self, record):
          if isinstance(record, list):
              return [self.transform(r) for r in record]
          return self.prefix + record

  write:

      def transform(self, record):
          return self._add_prefix(record)

      def _add_prefix(self, record):
          if isinstance(record, list):
              return [self._add_prefix(r) for r in record]
          return self.prefix + record

  If the method only calls itself in order to handle lists, it may be
  simpler to put type hints on transform() and let BaseModule do the
  work, as most transforms do:

      def transform(self, record: str) -> str:
          if not self.can_process_record(record):
              return self.digest_record(record)
          return self.prefix + record

  For worked examples see TimestampTransform._add_timestamp() and
  LogfileReader._read(). The convention is described in the BaseModule
  docstring in logger/utils/base_module.py; background is in issue #648.
"""


class TestMirrorConvention(unittest.TestCase):
    """If a Reader or Transform has a mirror_to writer, every call to its
    read() or transform() method is mirrored. So those methods must not
    call themselves to do internal work, such as processing the elements
    of a list; they should use a private helper method or digest_record()
    instead. See the BaseModule docstring and issue #648."""

    def test_find_self_calls(self):
        source = """
class GoodTransform:
    def transform(self, record):
        return self._helper(record)

    def _helper(self, record):
        if isinstance(record, list):
            return [self._helper(r) for r in record]
        return other.transform(record)

class BadTransform:
    def transform(self, record):
        if isinstance(record, list):
            return [self.transform(r) for r in record]
        return record

class GoodReader:
    def read(self):
        return self.file.read()

    def read_range(self, start, stop):
        return [self.read() for _ in range(start, stop)]

class BadReader:
    def read(self):
        return self.read()
"""
        self.assertEqual(find_self_calls(source),
                         [(14, 'BadTransform.transform() calls self.transform()'),
                          (26, 'BadReader.read() calls self.read()')])

    def test_no_self_calls(self):
        problems = []
        for module_dir in MODULE_DIRS:
            pattern = os.path.join(REPO_ROOT, module_dir, '**', '*.py')
            for path in sorted(glob.glob(pattern, recursive=True)):
                with open(path) as f:
                    source = f.read()
                try:
                    found = find_self_calls(source)
                except SyntaxError:
                    continue
                rel_path = os.path.relpath(path, REPO_ROOT)
                problems.extend(f'{rel_path}:{line}: {description}'
                                for line, description in found)

        if problems:
            self.fail(SELF_CALL_MESSAGE.format(
                count=len(problems),
                problems='\n'.join('  ' + problem for problem in problems)))


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
