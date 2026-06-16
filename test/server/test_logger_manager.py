#!/usr/bin/env python3

import logging
import os
import tempfile
import time
import unittest
import warnings

from logger.writers.text_file_writer import TextFileWriter  # noqa: E402
from server.in_memory_server_api import InMemoryServerAPI  # noqa: E402
from server.logger_manager import LoggerManager  # noqa: E402

SAMPLE_DATA = """Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation files
(the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell...""".split('\n')


############################
def make_cruise_definition(source_file, dest_file, tail=True):
    """Assemble a minimal one-logger cruise definition whose 'on' config
    reads source_file and writes dest_file. If tail is False, the logger
    process will exit as soon as it has read the source file - useful for
    testing the restart-on-death logic.
    """
    return {
        'cruise': {'id': 'TEST'},
        'loggers': {
            'test': {'configs': ['test->off', 'test->on']}
        },
        'modes': {
            'off': {'test': 'test->off'},
            'on': {'test': 'test->on'},
        },
        'default_mode': 'off',
        'configs': {
            'test->off': {},
            'test->on': {
                'readers': {
                    'class': 'TextFileReader',
                    'kwargs': {'file_spec': source_file,
                               'interval': 0.01,
                               'tail': tail}
                },
                'writers': {
                    'class': 'TextFileWriter',
                    'kwargs': {'filename': dest_file}
                }
            }
        }
    }


############################
class RecordingWriter:
    """Stand-in for the manager's CachedDataWriter; just records what it's
    given."""

    def __init__(self):
        self.records = []

    def write(self, record):
        self.records.append(record)

    def close(self):
        pass


################################################################################
class TestLoggerManager(unittest.TestCase):
    ############################
    def setUp(self):
        # To suppress resource warnings about unclosed files
        warnings.simplefilter('ignore', ResourceWarning)

        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_dir_name = self.temp_dir.name

        self.source_name = self.temp_dir_name + '/source.txt'
        self.dest_name = self.temp_dir_name + '/dest.txt'
        self.stderr_file_pattern = self.temp_dir_name + '/{logger}.stderr'

        # Create the source file
        writer = TextFileWriter(self.source_name)
        for line in SAMPLE_DATA:
            writer.write(line)

    ############################
    def _make_manager(self, cruise_definition, **kwargs):
        api = InMemoryServerAPI()
        api.load_configuration(cruise_definition)
        manager = LoggerManager(api=api,
                                stderr_file_pattern=self.stderr_file_pattern,
                                interval=0.1, **kwargs)
        return api, manager

    ############################
    def _wait_for(self, condition, timeout=10):
        """Wait until condition() returns True, or fail."""
        end_time = time.time() + timeout
        while time.time() < end_time:
            if condition():
                return
            time.sleep(0.1)
        self.fail('Timed out waiting for condition')

    ############################
    def test_start_stop_via_modes(self):
        """Loggers should start/stop to track the active mode."""
        cruise_definition = make_cruise_definition(self.source_name,
                                                   self.dest_name)
        api, manager = self._make_manager(cruise_definition)

        # Default mode is 'off'; its config is unrunnable, so EXITED.
        manager.update_configs()
        status = manager.get_status()
        self.assertEqual(status['test']['config'], 'test->off')
        self.assertEqual(status['test']['status'], 'EXITED')

        # Switch to 'on'; logger should start running and write output.
        api.set_active_mode('on')
        manager.update_configs()
        self._wait_for(
            lambda: manager.get_status()['test']['status'] == 'RUNNING')
        self._wait_for(lambda: os.path.exists(self.dest_name))

        # Switch back to 'off'; logger should be shut down.
        api.set_active_mode('off')
        manager.update_configs()
        status = manager.get_status()
        self.assertEqual(status['test']['config'], 'test->off')
        self.assertEqual(status['test']['status'], 'EXITED')

        manager.quit()
        self.assertEqual(manager.get_status(), {})

    ############################
    def test_restart_and_fail(self):
        """A logger that dies repeatedly should be restarted - driven by the
        stderr pipe-EOF death signal, with no polling - up to max_tries
        times, then declared FAILED."""
        # tail=False, so the logger process exits once it's read the file.
        cruise_definition = make_cruise_definition(self.source_name,
                                                   self.dest_name, tail=False)
        api, manager = self._make_manager(cruise_definition,
                                          max_tries=2, min_uptime=1000)
        api.set_active_mode('on')
        manager.update_configs()

        # Each death should trigger a restart via the death callback; after
        # max_tries rapid deaths the logger should be declared FAILED. Note
        # that we never call _check_loggers() - there is no polling here.
        self._wait_for(
            lambda: manager.get_status()['test']['status'] == 'FAILED',
            timeout=30)

        state = manager.logger_states['test']
        self.assertEqual(state.restart_count, 2)
        self.assertTrue(state.runner.is_failed())

        # Once failed, the polling check should leave it failed too.
        manager._check_loggers()
        self.assertTrue(state.runner.is_failed())

        manager.quit()

    ############################
    def test_stderr_forwarded_to_data_server(self):
        """The stderr of a logger that crashes on startup should still reach
        the data server writer, via the runner's relay and the manager's
        callback."""
        cruise_definition = make_cruise_definition(self.source_name,
                                                   self.dest_name)
        api, manager = self._make_manager(cruise_definition)
        manager.data_server_writer = RecordingWriter()

        bad_config = {
            'name': 'test->bad',
            'readers': {'class': 'NoSuchReaderClass', 'kwargs': {}},
            'writers': {'class': 'TextFileWriter',
                        'kwargs': {'filename': self.dest_name}}
        }
        manager._apply_configs({'test': bad_config})

        def stderr_arrived():
            return any('NoSuchReaderClass' in str(record.fields)
                       for record in manager.data_server_writer.records)
        self._wait_for(stderr_arrived)

        # Check the record is labeled the way the console expects
        for record in manager.data_server_writer.records:
            self.assertIn('stderr:logger:test', record.fields)

        manager.quit()

    ############################
    def test_max_tries_zero_retries_forever(self):
        """With max_tries=0, a dying logger should never be declared FAILED."""
        cruise_definition = make_cruise_definition(self.source_name,
                                                   self.dest_name, tail=False)
        api, manager = self._make_manager(cruise_definition,
                                          max_tries=0, min_uptime=1000)
        api.set_active_mode('on')
        manager.update_configs()

        # Death-callback-driven restarts should just keep coming.
        state = manager.logger_states['test']
        self._wait_for(lambda: state.restart_count >= 3, timeout=30)

        self.assertFalse(state.runner.is_failed())
        self.assertNotEqual(manager.get_status()['test']['status'], 'FAILED')
        manager.quit()


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
