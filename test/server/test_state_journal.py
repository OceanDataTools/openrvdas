#!/usr/bin/env python3
"""Tests for the logger manager's state journal (issue #670)."""
import datetime
import glob
import hashlib
import json
import logging
import os
import tempfile
import threading
import time
import unittest
import warnings
from unittest import mock

import yaml

from logger.readers.logfile_reader import LogfileReader  # noqa: E402
from logger.utils.read_config import read_config, expand_cruise_definition  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.writers.text_file_writer import TextFileWriter  # noqa: E402
from server.in_memory_server_api import InMemoryServerAPI  # noqa: E402
from server.logger_manager import LoggerManager  # noqa: E402
from server.state_journal import StateJournal, config_hash  # noqa: E402
from test.server.test_logger_manager import SAMPLE_DATA, make_cruise_definition  # noqa: E402


################################################################################
class TestStateJournal(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.filebase = os.path.join(self.temp_dir.name, 'journal')

    def entries(self):
        lines = []
        for path in sorted(glob.glob(self.filebase + '-*')):
            with open(path) as f:
                lines.extend(json.loads(line)['fields'] for line in f)
        return lines

    def test_records_json_lines_in_daily_files(self):
        journal = StateJournal(self.filebase)
        journal.record('mode_changed', **{'from': 'off'}, to='on')
        journal.record('logger_started', logger='gyro', config='gyro->on')
        files = glob.glob(self.filebase + '-*')
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0], r'journal-\d{4}-\d{2}-\d{2}$')
        entries = self.entries()
        self.assertEqual([e['event'] for e in entries], ['mode_changed', 'logger_started'])
        self.assertEqual(entries[0]['from'], 'off')
        self.assertRegex(entries[0]['time'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$')

    def test_lines_are_das_records(self):
        journal = StateJournal(self.filebase)
        journal.record('config_changed', logger='gyro', **{'from': 'gyro-off'},
                       to='gyro-on', loaded=datetime.datetime(2026, 10, 22, 12, 0))
        with open(glob.glob(self.filebase + '-*')[0]) as f:
            line = f.readline()
        record = DASRecord(json_str=line)
        self.assertEqual(record.data_id, 'logger_manager')
        self.assertEqual(record.message_type, 'config_changed')
        self.assertAlmostEqual(record.timestamp, time.time(), delta=5)
        self.assertEqual(record.fields['logger'], 'gyro')
        self.assertEqual(record.fields['from'], 'gyro-off')
        self.assertEqual(record.fields['loaded'], '2026-10-22 12:00:00')

    def test_logfile_reader_reads_the_journal(self):
        """A LogfileReader given the journal's filebase returns its entries
        as DASRecords, so a logger can send them to any writer."""
        journal = StateJournal(self.filebase)
        journal.record('mode_changed', **{'from': 'off'}, to='on')
        journal.record('logger_started', logger='gyro', config='gyro->on')
        reader = LogfileReader(filebase=self.filebase)
        records = [reader.read(), reader.read()]
        self.assertTrue(all(isinstance(r, DASRecord) for r in records))
        self.assertEqual([r.message_type for r in records],
                         ['mode_changed', 'logger_started'])
        self.assertEqual(records[1].fields['logger'], 'gyro')
        self.assertIsNone(reader.read())

    def test_logfile_reader_follows_the_journal(self):
        """With tail=True, a LogfileReader picks up entries as they're
        written."""
        journal = StateJournal(self.filebase)
        journal.record('manager_start', host='test')
        reader = LogfileReader(filebase=self.filebase, tail=True, refresh_file_spec=True)
        self.assertEqual(reader.read().message_type, 'manager_start')

        result = []
        thread = threading.Thread(target=lambda: result.append(reader.read()), daemon=True)
        thread.start()
        time.sleep(0.3)
        journal.record('mode_changed', **{'from': 'off'}, to='on')
        thread.join(timeout=10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].message_type, 'mode_changed')
        self.assertEqual(result[0].fields['to'], 'on')

    def test_disabled(self):
        StateJournal(None).record('mode_changed', to='on')
        StateJournal('').record('mode_changed', to='on')
        self.assertEqual(os.listdir(self.temp_dir.name), [])

    def test_unwritable_location_warns_once_and_never_raises(self):
        with self.assertLogs(level='WARNING') as logs:
            journal = StateJournal('/nonexistent/directory/journal')
            journal.record('mode_changed', to='on')
            journal.record('mode_changed', to='off')
        self.assertEqual(len(logs.output), 1)
        self.assertIn('cannot write', logs.output[0])

    def test_config_hash(self):
        a = {'readers': {'class': 'UDPReader', 'kwargs': {'port': 6224}}, 'name': 'x'}
        b = {'name': 'x', 'readers': {'kwargs': {'port': 6224}, 'class': 'UDPReader'}}
        self.assertEqual(config_hash(a), config_hash(b))
        self.assertEqual(len(config_hash(a)), 64)
        b['readers']['kwargs']['port'] = 6225
        self.assertNotEqual(config_hash(a), config_hash(b))


################################################################################
class TestLoggerManagerJournal(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter('ignore', ResourceWarning)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        tmp = self.temp_dir.name
        self.source = os.path.join(tmp, 'source.txt')
        self.dest = os.path.join(tmp, 'dest.txt')
        self.filebase = os.path.join(tmp, 'journal')
        writer = TextFileWriter(self.source)
        for line in SAMPLE_DATA:
            writer.write(line)
        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)

    def make_manager(self, definition, **kwargs):
        api = InMemoryServerAPI()
        api.load_configuration(definition)
        manager = LoggerManager(api=api, interval=0.1,
                                stderr_file_pattern=self.temp_dir.name + '/{logger}.stderr',
                                state_journal=self.filebase, **kwargs)
        self.addCleanup(manager.quit)
        return api, manager

    def entries(self, event=None):
        lines = []
        for path in sorted(glob.glob(self.filebase + '-*')):
            with open(path) as f:
                lines.extend(json.loads(line)['fields'] for line in f)
        return [e for e in lines if event is None or e['event'] == event]

    def wait_for(self, condition, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            if condition():
                return
            time.sleep(0.1)
        self.fail('Timed out waiting for condition')

    ############################
    def test_modes_and_configs(self):
        definition = make_cruise_definition(self.source, self.dest)
        api, manager = self.make_manager(definition)
        manager.update_configs()
        api.set_active_mode('on')
        manager.update_configs()
        self.wait_for(lambda: manager.get_status()['test']['status'] == 'RUNNING')
        running_config = manager.logger_states['test'].config
        api.set_active_mode('off')
        manager.update_configs()
        manager.quit()

        events = [(e['event'], e.get('from'), e.get('to'), e.get('config'))
                  for e in self.entries()]
        self.assertEqual(events, [
            ('manager_start', None, None, None),
            ('mode_changed', None, 'off', None),
            ('logger_started', None, None, 'test->off'),
            ('mode_changed', 'off', 'on', None),
            ('config_changed', 'test->off', 'test->on', None),
            ('mode_changed', 'on', 'off', None),
            ('config_changed', 'test->on', 'test->off', None),
            ('logger_stopped', None, None, 'test->off'),
            ('manager_stop', None, None, None),
        ])

        # The hash identifies the exact config that was started
        changed = self.entries('config_changed')[0]
        self.assertEqual(changed['config_sha256'], config_hash(running_config))
        self.assertIsInstance(changed['pid'], int)

    def test_mode_change_without_config_change(self):
        """A mode change that changes no config is noticed by the status loop."""
        definition = make_cruise_definition(self.source, self.dest)
        definition['modes']['also_off'] = {'test': 'test->off'}
        api, manager = self.make_manager(definition)
        manager.update_configs()
        api.set_active_mode('also_off')
        manager.update_configs()
        manager._send_status()
        self.assertEqual([(e['from'], e['to']) for e in self.entries('mode_changed')],
                         [(None, 'off'), ('off', 'also_off')])
        self.assertEqual(self.entries('config_changed'), [])

    def test_crash_loop_recorded_once_then_failure(self):
        """A crash loop gives one logger_crashed line and one logger_failed
        line carrying the count - not a line per crash."""
        definition = make_cruise_definition(self.source, self.dest, tail=False)
        api, manager = self.make_manager(definition, max_tries=3, min_uptime=1000)
        api.set_active_mode('on')
        manager.update_configs()
        self.wait_for(lambda: manager.get_status()['test']['status'] == 'FAILED', timeout=30)

        self.assertEqual(len(self.entries('logger_crashed')), 1)
        self.assertEqual(self.entries('logger_crashed')[0]['config'], 'test->on')
        failed = self.entries('logger_failed')
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]['crashes'], 3)

    def test_recovery_reports_number_of_crashes(self):
        definition = make_cruise_definition(self.source, self.dest)
        api, manager = self.make_manager(definition, min_uptime=1)
        api.set_active_mode('on')
        manager.update_configs()
        self.wait_for(lambda: manager.get_status()['test']['status'] == 'RUNNING')

        # Pretend the running logger had crashed three times in the last
        # minute before it was last started
        state = manager.logger_states['test']
        state.crash_count = 3
        state.crash_episode_start = time.time() - 60
        state.last_started = time.time() - 2

        manager._check_loggers()
        manager._check_loggers()   # recorded once, not again
        recovered = self.entries('logger_recovered')
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]['crashes'], 3)
        self.assertAlmostEqual(recovered[0]['crashing_for_seconds'], 58, delta=2)
        self.assertEqual(state.crash_count, 0)

    def test_not_yet_recovered(self):
        """Not recovered until it has stayed up for min_uptime."""
        definition = make_cruise_definition(self.source, self.dest)
        api, manager = self.make_manager(definition, min_uptime=1000)
        api.set_active_mode('on')
        manager.update_configs()
        self.wait_for(lambda: manager.get_status()['test']['status'] == 'RUNNING')
        manager.logger_states['test'].crash_count = 2
        manager.logger_states['test'].crash_episode_start = time.time()
        manager._check_loggers()
        self.assertEqual(self.entries('logger_recovered'), [])

    def test_stop_during_crash_loop_carries_count(self):
        definition = make_cruise_definition(self.source, self.dest)
        api, manager = self.make_manager(definition)
        api.set_active_mode('on')
        manager.update_configs()
        manager.logger_states['test'].crash_count = 4
        api.set_active_mode('off')
        manager.update_configs()
        self.assertEqual(self.entries('config_changed')[-1]['crashes_before_change'], 4)

    def test_definition_loaded(self):
        cruise_file = os.path.join(self.temp_dir.name, 'cruise.yaml')
        with open(cruise_file, 'w') as f:
            f.write('cruise: {id: TEST}\n')
        definition = make_cruise_definition(self.source, self.dest)
        definition['cruise']['config_filename'] = cruise_file
        api, manager = self.make_manager(definition)
        manager.load_definition_from_api()
        manager.load_definition_from_api()   # the same load, reported again
        loaded = self.entries('definition_loaded')
        self.assertEqual(len(loaded), 1)
        self.assertRegex(loaded[0]['loaded_time'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$')
        self.assertEqual(loaded[0]['cruise_id'], 'TEST')
        self.assertEqual(loaded[0]['filename'], cruise_file)
        self.assertEqual(len(loaded[0]['file_sha256']), 64)

    def test_manager_start_is_first(self):
        definition = make_cruise_definition(self.source, self.dest)
        api, manager = self.make_manager(definition)
        manager.update_configs()
        started = self.entries('manager_start')
        self.assertEqual(self.entries()[0]['event'], 'manager_start')
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0]['pid'], os.getpid())
        self.assertTrue(started[0]['openrvdas_version'])

    def test_code_version_of_each_start(self):
        """Each start and restart records the code it was started with, and
        a crash the code that crashed."""
        code = {'version': 'v1'}
        with mock.patch('server.config_snapshot.code_version', lambda: code['version']), \
                mock.patch('server.logger_manager.CODE_VERSION_CACHE_SECONDS', 0):
            definition = make_cruise_definition(self.source, self.dest)
            api, manager = self.make_manager(definition, min_uptime=1)
            manager.update_configs()
            code['version'] = 'v2'
            api.set_active_mode('on')
            manager.update_configs()
            self.wait_for(lambda: manager.get_status()['test']['status'] == 'RUNNING')

            # The code changes, and the logger crashes and is restarted
            code['version'] = 'v3'
            old_pid = manager._pid('test')
            manager.logger_states['test'].runner.process.kill()
            self.wait_for(lambda: manager._pid('test') not in (None, old_pid)
                          and manager.get_status()['test']['status'] == 'RUNNING')
            manager.logger_states['test'].last_started = time.time() - 2
            manager._check_loggers()

        self.assertEqual(self.entries('manager_start')[0]['code'], 'v1')
        self.assertEqual(self.entries('logger_started')[0]['code'], 'v1')
        self.assertEqual(self.entries('config_changed')[0]['code'], 'v2')
        self.assertEqual(self.entries('logger_crashed')[0]['code'], 'v2')
        self.assertEqual(self.entries('logger_recovered')[0]['code'], 'v3')

    def test_code_version_is_real(self):
        """Without mocking: the manager records the repository's version."""
        from server.config_snapshot import code_version
        definition = make_cruise_definition(self.source, self.dest)
        api, manager = self.make_manager(definition)
        manager.update_configs()
        self.assertEqual(self.entries('logger_started')[0]['code'], code_version())

    def test_journal_off(self):
        definition = make_cruise_definition(self.source, self.dest)
        api = InMemoryServerAPI()
        api.load_configuration(definition)
        manager = LoggerManager(api=api, interval=0.1,
                                stderr_file_pattern=self.temp_dir.name + '/{logger}.stderr')
        manager.update_configs()
        manager.quit()
        self.assertEqual(glob.glob(self.filebase + '*'), [])


################################################################################
TEMPLATE_FILE = """
logger_templates:
  probe_template:
    configs:
      'off': {}
      'on':
        readers: {class: TextFileReader, kwargs: {file_spec: <<source>>, tail: true}}
        writers: {class: TextFileWriter, kwargs: {filename: <<dest>>}}
"""

CRUISE_FILE = """
cruise: {id: FILES}
includes_base_dir: <<tmp>>
includes: [probe_template.yaml]
variables: {source: <<source>>, dest: <<dest>>}
loggers:
  probe: {logger_template: probe_template}
modes:
  'off': [probe-off]
  'on': [probe-on]
"""


class TestDefinitionFiles(unittest.TestCase):
    """The files a loaded definition is built from: recorded, watched, and
    snapshotted (issue #413)."""

    def setUp(self):
        warnings.simplefilter('ignore', ResourceWarning)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.tmp = os.path.realpath(self.temp_dir.name)
        self.filebase = os.path.join(self.tmp, 'journal')
        self.template = self.write('probe_template.yaml', TEMPLATE_FILE)
        self.cruise_file = self.write('cruise.yaml', CRUISE_FILE)
        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)

    def write(self, name, content):
        path = os.path.join(self.tmp, name)
        content = (content.replace('<<tmp>>', self.tmp)
                   .replace('<<source>>', os.path.join(self.tmp, 'source.txt'))
                   .replace('<<dest>>', os.path.join(self.tmp, 'dest.txt')))
        with open(path, 'w') as f:
            f.write(content)
        return path

    def make_manager(self, **kwargs):
        definition = expand_cruise_definition(read_config(self.cruise_file))
        definition['cruise']['config_filename'] = self.cruise_file
        api = InMemoryServerAPI()
        api.load_configuration(definition)
        manager = LoggerManager(api=api, interval=0.1,
                                stderr_file_pattern=self.tmp + '/{logger}.stderr',
                                **kwargs)
        self.addCleanup(manager.quit)
        manager.load_definition_from_api()
        return manager

    def entries(self, event):
        lines = []
        for path in sorted(glob.glob(self.filebase + '-*')):
            with open(path) as f:
                lines.extend(json.loads(line)['fields'] for line in f)
        return [e for e in lines if e['event'] == event]

    def sha256(self, path):
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()

    ############################
    def test_load_records_every_files_hash(self):
        self.make_manager(state_journal=self.filebase)
        loaded = self.entries('definition_loaded')[0]
        self.assertEqual(loaded['files'], {self.cruise_file: self.sha256(self.cruise_file),
                                           self.template: self.sha256(self.template)})

    def test_changed_file_is_journaled_once(self):
        manager = self.make_manager(state_journal=self.filebase)
        manager._check_definition_files()
        self.assertEqual(self.entries('definition_files_changed'), [])

        time.sleep(0.05)
        self.write('probe_template.yaml', TEMPLATE_FILE + '# edited\n')
        manager._check_definition_files()
        manager._check_definition_files()
        changed = self.entries('definition_files_changed')
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]['files'], {self.template: self.sha256(self.template)})

    def test_touching_a_file_without_changing_it_is_not_a_change(self):
        manager = self.make_manager(state_journal=self.filebase)
        os.utime(self.template, (time.time() + 10, time.time() + 10))
        manager._check_definition_files()
        self.assertEqual(self.entries('definition_files_changed'), [])

    def test_deleted_file_is_a_change(self):
        manager = self.make_manager(state_journal=self.filebase)
        os.remove(self.template)
        manager._check_definition_files()
        self.assertEqual(self.entries('definition_files_changed')[0]['files'],
                         {self.template: None})

    def test_snapshots_on_load_and_on_change(self):
        snapshot_dir = os.path.join(self.tmp, 'snapshots')
        os.makedirs(snapshot_dir)
        manager = self.make_manager(state_journal=self.filebase, snapshot_dir=snapshot_dir)
        self.wait_for(lambda: self.entries('snapshot_taken'))
        taken = self.entries('snapshot_taken')[0]
        self.assertEqual(taken['reason'], 'definition loaded')
        self.assertTrue(os.path.isfile(os.path.join(taken['path'], 'MANIFEST.yaml')))

        time.sleep(1.1)   # so the second snapshot gets a different name
        self.write('probe_template.yaml', TEMPLATE_FILE + '# edited\n')
        manager._check_definition_files()
        self.wait_for(lambda: len(self.entries('snapshot_taken')) == 2)
        self.assertEqual(self.entries('definition_files_changed')[0]['filename'],
                         self.cruise_file)
        changed = self.entries('snapshot_taken')[1]
        self.assertEqual(changed['reason'], 'definition files changed')
        with open(os.path.join(changed['path'], 'MANIFEST.yaml')) as f:
            manifest = yaml.safe_load(f)
        flags = {os.path.basename(e['source']): e['modified_after_load']
                 for e in manifest['files']}
        self.assertEqual(flags, {'cruise.yaml': False, 'probe_template.yaml': True})

    def test_snapshot_failure_is_journaled_not_raised(self):
        # A file where the snapshot directory should be: can't write into it
        not_a_directory = self.write('not_a_directory', 'just a file\n')
        manager = self.make_manager(state_journal=self.filebase, snapshot_dir=not_a_directory)
        self.wait_for(lambda: self.entries('snapshot_failed'))
        self.assertEqual(self.entries('snapshot_failed')[0]['reason'], 'definition loaded')
        self.assertEqual(self.entries('snapshot_taken'), [])
        manager.update_configs()   # and the manager carries on

    def test_nothing_listed_without_journal_or_snapshots(self):
        manager = self.make_manager()
        self.assertEqual(manager.definition_files, {})

    def wait_for(self, condition, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            if condition():
                return
            time.sleep(0.1)
        self.fail('Timed out waiting for condition')


if __name__ == '__main__':
    unittest.main()
