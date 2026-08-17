#!/usr/bin/env python3
"""Tests for logger/listener/listen.py: the config-dict construction path
(ListenerFromLoggerConfig) and the command-line assembly helpers."""

import copy
import logging
import tempfile
import unittest
import warnings

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
if __name__ == '__main__':
    unittest.main(warnings='ignore')
