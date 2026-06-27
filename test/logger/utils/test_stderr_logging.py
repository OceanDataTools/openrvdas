#!/usr/bin/env python3

import json
import logging
import threading
import unittest

from logger.utils.stderr_logging import StdErrLoggingHandler  # noqa: E402


############################
class RecordingWriter:
    """Just records what it's given."""

    def __init__(self):
        self.lines = []
        self.lock = threading.Lock()

    def write(self, line):
        with self.lock:
            self.lines.append(line)


############################
class RecursiveWriter:
    """Writer that logs from inside write() - to the very logger our
    handler is attached to - as a misbehaving writer might."""

    def __init__(self, logger):
        self.logger = logger
        self.lines = []

    def write(self, line):
        self.logger.warning('inner message from writer')
        self.lines.append(line)


############################
class FailingWriter:
    def write(self, line):
        raise ValueError('boom')


################################################################################
class TestStdErrLoggingHandler(unittest.TestCase):
    ############################
    def setUp(self):
        # A detached logger, so we don't tangle with the global config
        self.logger = logging.Logger('test_stderr_logging')

        # Don't let handleError() spew to stderr during the failure test
        self.saved_raise_exceptions = logging.raiseExceptions
        logging.raiseExceptions = False

    ############################
    def tearDown(self):
        logging.raiseExceptions = self.saved_raise_exceptions

    ############################
    def test_recursive_writer_does_not_recurse(self):
        """A writer that logs from inside write() should not recurse, and
        should not disturb the root logger's level."""
        writer = RecursiveWriter(self.logger)
        self.logger.addHandler(StdErrLoggingHandler(writer))
        root_level = logging.root.getEffectiveLevel()

        self.logger.warning('outer message')

        # Only the outer message should have been written; the inner one
        # was dropped by the reentrancy guard rather than recursing.
        self.assertEqual(len(writer.lines), 1)
        self.assertIn('outer message', writer.lines[0])
        self.assertEqual(logging.root.getEffectiveLevel(), root_level)

    ############################
    def test_failing_writer_does_not_propagate(self):
        """An exception inside a writer must not propagate to the code
        that called logging.*, and must not disturb the root level."""
        self.logger.addHandler(StdErrLoggingHandler(FailingWriter()))
        root_level = logging.root.getEffectiveLevel()

        try:
            self.logger.warning('this should not raise')
        except ValueError:
            self.fail('Writer exception propagated out of logging call')

        self.assertEqual(logging.root.getEffectiveLevel(), root_level)

    ############################
    def test_concurrent_emits_lose_nothing(self):
        """Many threads logging at once: every message should be written
        and the root logger's level should be untouched afterward."""
        writer = RecordingWriter()
        self.logger.addHandler(StdErrLoggingHandler(writer))
        root_level = logging.root.getEffectiveLevel()

        num_threads = 8
        msgs_per_thread = 50

        def hammer(thread_num):
            for i in range(msgs_per_thread):
                self.logger.warning('message %d from thread %d', i, thread_num)

        threads = [threading.Thread(target=hammer, args=(n,))
                   for n in range(num_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(writer.lines), num_threads * msgs_per_thread)
        self.assertEqual(logging.root.getEffectiveLevel(), root_level)

    ############################
    def test_parse_to_json(self):
        """parse_to_json should split DEFAULT_LOGGING_FORMAT into its five
        fields; in particular, filename:lineno must not end up glued to
        the front of the message."""
        writer = RecordingWriter()
        self.logger.addHandler(StdErrLoggingHandler(writer, parse_to_json=True))

        self.logger.warning('hello world')

        self.assertEqual(len(writer.lines), 1)
        fields = json.loads(writer.lines[0])
        self.assertEqual(fields['message'], 'hello world')
        self.assertEqual(fields['levelname'], 'WARNING')
        self.assertEqual(fields['levelno'], logging.WARNING)
        self.assertIn('test_stderr_logging.py', fields['fileline'])


################################################################################
if __name__ == '__main__':
    unittest.main(warnings='ignore')
