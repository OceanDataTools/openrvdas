#!/usr/bin/env python3
"""Tests for logger/listener/listen.py: the config-dict construction path
(ListenerFromLoggerConfig) and the command-line assembly helpers."""

import copy
import importlib
import logging
import os
import sys
import tempfile
import unittest
import warnings
from unittest import mock

from logger.listener.listen import (
    ListenerFromLoggerConfig, build_arg_parser, parse_addr_list, build_listener)
from logger.utils.stderr_logging import StdErrLoggingHandler


################################################################################
class TestListenFromConfig(unittest.TestCase):
    ############################
    def setUp(self):
        warnings.simplefilter('ignore', ResourceWarning)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.src = self.tmpdir.name + '/src.txt'
        with open(self.src, 'w') as f:
            f.write('line1\nline2\n')
        self.dest = self.tmpdir.name + '/dest.txt'

        # The stderr_writers path adds handlers to the root logger; snapshot
        # so we can restore and not leak into other tests.
        self._saved_handlers = list(logging.getLogger().handlers)

    ############################
    def tearDown(self):
        root = logging.getLogger()
        for h in list(root.handlers):
            if h not in self._saved_handlers:
                root.removeHandler(h)

    ############################
    def _config(self, **extra):
        cfg = {
            'readers': {'class': 'TextFileReader',
                        'kwargs': {'file_spec': self.src}},
            'writers': {'class': 'TextFileWriter',
                        'kwargs': {'filename': self.dest}},
        }
        cfg.update(extra)
        return cfg

    ############################
    def test_builds_from_dict(self):
        listener = ListenerFromLoggerConfig(self._config(name='demo'))
        self.assertEqual(listener.name, 'demo')

    ############################
    def test_deprecated_and_unknown_keys_tolerated(self):
        # The deprecated 'check_format' (and any unknown top-level key) must
        # be dropped with a warning rather than crashing the constructor.
        cfg = self._config(check_format=False, bogus_key=1, name='demo')
        with self.assertLogs(level=logging.WARNING) as logs:
            listener = ListenerFromLoggerConfig(cfg)
        self.assertEqual(listener.name, 'demo')
        joined = ' '.join(logs.output)
        self.assertIn('check_format', joined)
        self.assertIn('bogus_key', joined)

    ############################
    def test_config_dict_not_mutated(self):
        # Building a listener must not mutate the caller's config dict, and
        # the same dict must be reusable to build a second listener with its
        # stderr_writers intact (regression for the old del-on-input bug).
        cfg = self._config(
            stderr_writers={'class': 'TextFileWriter',
                            'kwargs': {'filename': self.tmpdir.name + '/err.txt'}})
        before = copy.deepcopy(cfg)

        ListenerFromLoggerConfig(cfg)
        self.assertEqual(cfg, before)
        self.assertIn('stderr_writers', cfg)

        # Second build from the same dict still sees stderr_writers.
        ListenerFromLoggerConfig(cfg)
        self.assertEqual(cfg, before)

    ############################
    def test_stderr_handler_added_once_per_build(self):
        # The stderr handler is installed exactly once per construction (at
        # the top level), not once per nested kwarg dict.
        root = logging.getLogger()

        def stderr_handler_count():
            return sum(isinstance(h, StdErrLoggingHandler) for h in root.handlers)

        cfg = self._config(
            stderr_writers={'class': 'TextFileWriter',
                            'kwargs': {'filename': self.tmpdir.name + '/err.txt'}})
        before = stderr_handler_count()
        ListenerFromLoggerConfig(cfg)
        self.assertEqual(stderr_handler_count() - before, 1)


################################################################################
class TestCLIHelpers(unittest.TestCase):
    ############################
    def setUp(self):
        warnings.simplefilter('ignore', ResourceWarning)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.src = self.tmpdir.name + '/src.txt'
        with open(self.src, 'w') as f:
            f.write('line1\nline2\n')
        self.dest = self.tmpdir.name + '/dest.txt'

    ############################
    def test_parse_addr_list(self):
        parser = build_arg_parser()
        self.assertEqual(parse_addr_list('6221', '--udp', parser),
                         [('', 6221)])
        self.assertEqual(
            parse_addr_list('1.2.3.4:6221,:6222', '--udp', parser),
            [('1.2.3.4', 6221), ('', 6222)])

    ############################
    def test_build_listener_cli_path(self):
        parser = build_arg_parser()
        argv = ['listen.py', '--file', self.src, '--write_file', self.dest]
        listener = build_listener(argv, parser)
        listener.run()
        with open(self.dest) as f:
            out = [line.rstrip() for line in f.readlines()]
        self.assertEqual(out, ['line1', 'line2'])

    ############################
    def test_build_listener_cli_with_transform(self):
        parser = build_arg_parser()
        argv = ['listen.py', '--file', self.src,
                '--transform_prefix', 'pre', '--write_file', self.dest]
        listener = build_listener(argv, parser)
        listener.run()
        with open(self.dest) as f:
            out = [line.rstrip() for line in f.readlines()]
        self.assertEqual(out, ['pre line1', 'pre line2'])


################################################################################
class TestImportModule(unittest.TestCase):
    """Configs may name modules that live in the OpenRVDAS tree but aren't
    installed as packages (contrib/, local/). Verify _import_module() finds
    them even when the OpenRVDAS root isn't on sys.path, which is the case
    when listen.py is run as a script or via its console entry point.
    """
    # 'contrib' is a namespace package with no third-party dependencies of
    # its own, which makes it a safe target to import in a test.
    UNINSTALLED_PACKAGE = 'contrib'

    ############################
    def setUp(self):
        self.orig_sys_path = list(sys.path)
        self.orig_modules = dict(sys.modules)
        self.openrvdas_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.realpath(__file__)))))
        # Simulate script invocation: OpenRVDAS root not on sys.path, and the
        # package not already imported by some earlier test.
        sys.path[:] = [p for p in sys.path
                       if os.path.realpath(p or os.getcwd()) != self.openrvdas_root]
        sys.modules.pop(self.UNINSTALLED_PACKAGE, None)

    ############################
    def tearDown(self):
        sys.path[:] = self.orig_sys_path
        sys.modules.clear()
        sys.modules.update(self.orig_modules)

    ############################
    def test_plain_import_fails_without_root(self):
        """Guard the premise: without the root on sys.path, a plain import
        of an uninstalled package really does fail. If this ever starts
        passing, the test below is no longer proving anything."""
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module(self.UNINSTALLED_PACKAGE)

    ############################
    def test_import_module_adds_root_and_succeeds(self):
        module = ListenerFromLoggerConfig._import_module(self.UNINSTALLED_PACKAGE)
        self.assertIsNotNone(module)
        self.assertIn(self.openrvdas_root, sys.path)

    ############################
    def test_genuinely_missing_module_still_raises(self):
        """A typo'd or absent module must still fail, not be papered over."""
        with self.assertRaises(ModuleNotFoundError):
            ListenerFromLoggerConfig._import_module('no_such_module_xyzzy')

    ############################
    def test_missing_sub_dependency_is_not_masked(self):
        """If the module itself is found but one of *its* imports fails - e.g.
        a contrib driver whose hardware library isn't installed - the error
        must propagate immediately, with no pointless second attempt."""
        err = ModuleNotFoundError("No module named 'somedep'", name='somedep')
        with mock.patch('importlib.import_module', side_effect=err) as mock_import:
            with self.assertRaises(ModuleNotFoundError) as ctx:
                ListenerFromLoggerConfig._import_module('contrib.some.driver')
        self.assertEqual(ctx.exception.name, 'somedep')
        self.assertEqual(mock_import.call_count, 1)  # no retry


################################################################################
if __name__ == '__main__':
    unittest.main(warnings='ignore')
