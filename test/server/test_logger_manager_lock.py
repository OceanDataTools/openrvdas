#!/usr/bin/env python3
"""Tests that only one logger manager runs on a host at a time (#686)."""
import glob
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import unittest

from server.logger_manager import AnotherManagerRunning, acquire_lock  # noqa: E402

OPENRVDAS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAcquireLock(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.lock_file = os.path.join(self.temp_dir.name, 'run', 'logger_manager.lock')

    def read(self):
        with open(self.lock_file) as f:
            return f.read()

    def test_lock_records_pid_and_refuses_a_second(self):
        lock = acquire_lock(self.lock_file)   # also creates the directory
        self.assertIsNotNone(lock)
        self.assertEqual(self.read(), f'{os.getpid()}\n')

        # A second lock - even from the same process - is refused, naming us
        with self.assertRaises(AnotherManagerRunning) as cm:
            acquire_lock(self.lock_file)
        self.assertEqual(cm.exception.running_pid, str(os.getpid()))
        self.assertEqual(self.read(), f'{os.getpid()}\n')   # and left intact

        # Once released, it can be taken again
        lock.close()
        lock = acquire_lock(self.lock_file)
        self.assertIsNotNone(lock)
        lock.close()

    def test_pid_left_by_a_dead_manager_is_no_obstacle(self):
        """The lock dies with the process; a pid left in the file is ignored."""
        os.makedirs(os.path.dirname(self.lock_file))
        with open(self.lock_file, 'w') as f:
            f.write('99999\n')
        lock = acquire_lock(self.lock_file)
        self.assertIsNotNone(lock)
        self.assertEqual(self.read(), f'{os.getpid()}\n')
        lock.close()

    def test_lock_that_cant_be_opened_doesnt_stop_the_manager(self):
        not_a_dir = os.path.join(self.temp_dir.name, 'file')
        open(not_a_dir, 'w').close()
        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.assertIsNone(acquire_lock(os.path.join(not_a_dir, 'logger_manager.lock')))


class TestLoggerManagerStartup(unittest.TestCase):
    """Run logger_manager.py itself while this test holds its lock."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.lock_file = os.path.join(self.temp_dir.name, 'logger_manager.lock')
        self.journal = os.path.join(self.temp_dir.name, 'journal')
        self.lock = acquire_lock(self.lock_file)
        self.addCleanup(self.lock.close)

    def start_manager(self, lock_file):
        env = dict(os.environ, PYTHONPATH=OPENRVDAS_ROOT)
        return subprocess.Popen(
            [sys.executable, 'server/logger_manager.py', '--database', 'memory',
             '--no-console', '--lock_file', lock_file, '--state_journal', self.journal],
            cwd=OPENRVDAS_ROOT, env=env, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, text=True)

    def journal_events(self, event):
        entries = []
        for path in glob.glob(self.journal + '-*'):
            with open(path) as f:
                entries.extend(json.loads(line)['fields'] for line in f)
        return [e for e in entries if e['event'] == event]

    def test_second_manager_refuses_to_start(self):
        manager = self.start_manager(self.lock_file)
        try:
            _, stderr = manager.communicate(timeout=60)
        finally:
            manager.kill()
        self.assertEqual(manager.returncode, 1)
        self.assertIn(f'Another logger manager (pid {os.getpid()})', stderr)
        self.assertIn('--lock_file none', stderr)

        refused = self.journal_events('manager_refused')
        self.assertEqual(len(refused), 1)
        self.assertEqual(refused[0]['running_pid'], str(os.getpid()))
        self.assertEqual(refused[0]['pid'], manager.pid)
        self.assertEqual(self.journal_events('manager_start'), [])

    def test_lock_file_none_skips_the_check(self):
        manager = self.start_manager('none')
        try:
            time.sleep(5)
            self.assertIsNone(manager.poll(), 'manager exited despite --lock_file none')
        finally:
            manager.terminate()
            manager.communicate(timeout=30)


if __name__ == '__main__':
    unittest.main()
