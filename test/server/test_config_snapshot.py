#!/usr/bin/env python3
"""Tests for server/config_snapshot.py (issue #413)."""
import datetime
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
import unittest
from contextlib import redirect_stdout

import yaml

from server import config_snapshot  # noqa: E402
from server.state_journal import StateJournal, config_hash  # noqa: E402
from logger.utils import read_config  # noqa: E402

TEMPLATE = """
logger_templates:
  gyro_template:
    configs:
      'off': {}
      'on':
        readers:
          class: UDPReader
          kwargs: {port: <<port>>}
        transforms:
        - class: ParseTransform
          kwargs:
            definition_path: <<tmp>>/devices/ship_devices.yaml
        writers:
        - class: LogfileWriter
          kwargs:
            filebase: /var/tmp/log/gyro
            header_file: <<tmp>>/header.txt
        - class: InfluxDBWriter
          kwargs:
            bucket_name: test
            auth_token: not-a-real-token
"""

CRUISE = """
cruise:
  id: TEST01
includes_base_dir: <<tmp>>
includes:
  - templates/*.yaml
variables:
  tmp: <<tmp>>
loggers:
  gyro:
    logger_template: gyro_template
    variables: {port: 6224}
  knud:
    configs:
      'off': {}
      'on':
        readers: {class: UDPReader, kwargs: {port: 6225}}
        transforms:
        - class: ParseTransform   # no definition_path: uses the default
        writers: {class: TextFileWriter}
modes:
  'off': [gyro-off, knud-off]
  'on': [gyro-on, knud-on]
"""

DEVICES = """
includes_base_dir: <<tmp>>
includes:
  - devices/types.yaml
devices:
  gyro:
    category: device
    device_type: Gyro
"""

TYPES = """
device_types:
  Gyro:
    category: device_type
    format: "$HEHDT,{HeadingTrue:f},T*{CheckSum:x}"
"""


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


class SnapshotTestCase(unittest.TestCase):
    """A temporary cruise to snapshot; shared by the test classes below."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.tmp = os.path.realpath(self.tmpdir.name)
        self.output = os.path.join(self.tmp, 'snapshots')
        os.makedirs(self.output)
        for rel, content in (('cruise.yaml', CRUISE),
                             ('templates/gyro_template.yaml', TEMPLATE),
                             ('devices/ship_devices.yaml', DEVICES),
                             ('devices/types.yaml', TYPES),
                             ('header.txt', 'Cruise TEST01, gyro\n')):
            self.write(rel, content.replace('<<tmp>>', self.tmp))
        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)

    def write(self, rel, content):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def snapshot(self, **kwargs):
        # Don't pick up a journal from wherever the tests happen to run
        kwargs.setdefault('journal', None)
        path = config_snapshot.take_snapshot(os.path.join(self.tmp, 'cruise.yaml'),
                                             output_dir=self.output, **kwargs)
        with open(os.path.join(path, 'MANIFEST.yaml')) as f:
            return path, yaml.safe_load(f)

    def source(self, manifest, name):
        """The manifest entry for the captured file with this source path."""
        matches = [f for f in manifest['files'] if f['source'] == name]
        self.assertEqual(len(matches), 1, name)
        return matches[0]


class TestCruiseSnapshot(SnapshotTestCase):

    ############################
    def test_captures_every_file_the_definition_uses(self):
        path, manifest = self.snapshot()
        captured = {f['source'] for f in manifest['files']}
        for rel in ('cruise.yaml', 'templates/gyro_template.yaml',
                    'devices/ship_devices.yaml', 'devices/types.yaml', 'header.txt'):
            self.assertIn(os.path.join(self.tmp, rel), captured)
        # The ParseTransform with no definition_path uses the default files
        self.assertIn(os.path.join(config_snapshot.OPENRVDAS_ROOT,
                                   'logger', 'devices', 'NMEA_0183.yaml'), captured)
        self.assertEqual(manifest['warnings'], [])

    def test_copies_are_exact_and_hashes_recorded(self):
        path, manifest = self.snapshot()
        for entry in manifest['files']:
            copy = os.path.join(path, entry['path'])
            self.assertTrue(os.path.isfile(copy), entry['path'])
            self.assertEqual(sha256(copy), entry['sha256'])
            self.assertEqual(entry['sha256'], sha256(entry['source']))

    def test_paths_keep_their_layout(self):
        """Files in the OpenRVDAS tree keep their relative paths; others go
        under sources/_abs/ at their absolute path."""
        path, manifest = self.snapshot()
        nmea = os.path.join(config_snapshot.OPENRVDAS_ROOT, 'logger/devices/NMEA_0183.yaml')
        self.assertEqual(self.source(manifest, nmea)['path'],
                         'sources/logger/devices/NMEA_0183.yaml')
        cruise = os.path.join(self.tmp, 'cruise.yaml')
        self.assertEqual(self.source(manifest, cruise)['path'],
                         os.path.join('sources', '_abs', cruise.lstrip(os.sep)))

    def test_expanded_definition_redacts_secrets(self):
        path, manifest = self.snapshot()
        with open(os.path.join(path, 'expanded_config.yaml')) as f:
            text = f.read()
        self.assertNotIn('not-a-real-token', text)
        expanded = yaml.safe_load(text)
        writer = expanded['configs']['gyro-on']['writers'][1]
        self.assertEqual(writer['kwargs']['auth_token'], config_snapshot.REDACTED)
        self.assertEqual(writer['kwargs']['bucket_name'], 'test')
        self.assertTrue(manifest['snapshot']['secrets_redacted'])

        path, manifest = self.snapshot(redact_secrets=False)
        with open(os.path.join(path, 'expanded_config.yaml')) as f:
            self.assertIn('not-a-real-token', f.read())

    def test_secrets_in_source_files_are_flagged(self):
        path, manifest = self.snapshot()
        template = self.source(manifest, os.path.join(self.tmp, 'templates/gyro_template.yaml'))
        lines = TEMPLATE.split('\n')
        self.assertEqual([lines[n - 1].strip() for n in template['possible_secrets_on_lines']],
                         ['auth_token: not-a-real-token'])
        self.assertNotIn('possible_secrets_on_lines',
                         self.source(manifest, os.path.join(self.tmp, 'cruise.yaml')))

    def test_files_changed_after_load_are_flagged(self):
        loaded = datetime.datetime.now(datetime.timezone.utc)
        time.sleep(0.05)
        self.write('devices/types.yaml', TYPES + '# edited after loading\n')
        path, manifest = self.snapshot(loaded_time=loaded)
        flags = {os.path.relpath(f['source'], self.tmp): f['modified_after_load']
                 for f in manifest['files'] if f['source'].startswith(self.tmp)}
        self.assertTrue(flags['devices/types.yaml'])
        self.assertFalse(flags['cruise.yaml'])

    def test_environment_and_repositories(self):
        path, manifest = self.snapshot()
        environment = manifest['environment']
        for key in ('openrvdas_version', 'hostname', 'os', 'python', 'packages'):
            self.assertTrue(environment[key], key)
        self.assertIn('PyYAML', environment['packages'])

        # The temporary files aren't in git; the default definitions are
        self.assertEqual(self.source(manifest, os.path.join(self.tmp, 'cruise.yaml'))['git'],
                         'not in a git repository')
        nmea = os.path.join(config_snapshot.OPENRVDAS_ROOT, 'logger/devices/NMEA_0183.yaml')
        if self.source(manifest, nmea).get('git') != 'not in a git repository':
            repo = manifest['repositories'][0]
            self.assertEqual(len(repo['commit']), 40)
            self.assertIn('untracked_code', repo)
            if repo['uncommitted_changes']:
                self.assertTrue(os.path.isfile(os.path.join(path, repo['patch'])))

    def test_tar(self):
        path = config_snapshot.take_snapshot(os.path.join(self.tmp, 'cruise.yaml'),
                                             output_dir=self.output, make_tar=True,
                                             journal=None)
        self.assertTrue(path.endswith('.tar.gz'))
        with tarfile.open(path) as tar:
            names = tar.getnames()
        name = os.path.basename(path)[:-len('.tar.gz')]
        self.assertTrue(name.startswith('TEST01_'))
        self.assertIn(f'{name}/MANIFEST.yaml', names)
        self.assertIn(f'{name}/expanded_config.yaml', names)

    def test_command_line(self):
        output = io.StringIO()
        with redirect_stdout(output):
            config_snapshot.main([os.path.join(self.tmp, 'cruise.yaml'),
                                  '--output', self.output, '--journal', 'none',
                                  '--loaded-time', '2026-01-01T00:00:00Z'])
        path = output.getvalue().strip()
        with open(os.path.join(path, 'MANIFEST.yaml')) as f:
            manifest = yaml.safe_load(f)
        self.assertEqual(manifest['snapshot']['cruise_definition_loaded'],
                         '2026-01-01T00:00:00Z')

    def test_snapshots_in_the_same_second_dont_collide(self):
        paths = [self.snapshot()[0] for _ in range(3)]
        self.assertEqual(len(set(paths)), 3)
        for path in paths:
            self.assertTrue(os.path.isfile(os.path.join(path, 'MANIFEST.yaml')))

    def test_unreadable_definition(self):
        with self.assertRaises(ValueError):
            config_snapshot.take_snapshot(os.path.join(self.tmp, 'missing.yaml'),
                                          output_dir=self.output, journal=None)

    def test_symlinks_record_what_they_resolve_to(self):
        """A link to the current dated file records which file that was (#679)."""
        types = os.path.join(self.tmp, 'devices', 'types.yaml')
        dated = os.path.join(self.tmp, 'devices', 'types_2026-10-01.yaml')
        os.rename(types, dated)
        os.symlink('types_2026-10-01.yaml', types)

        path, manifest = self.snapshot()
        entry = self.source(manifest, types)
        self.assertEqual(entry['resolves_to'], dated)
        self.assertEqual(entry['sha256'], sha256(dated))
        # Files that aren't reached through a symlink don't say so
        self.assertNotIn('resolves_to',
                         self.source(manifest, os.path.join(self.tmp, 'cruise.yaml')))


class TestSnapshotJournal(SnapshotTestCase):
    """What a snapshot takes from the logger manager's journal (#670)."""

    def setUp(self):
        super().setUp()
        self.journal_base = os.path.join(self.tmp, 'logs', 'logger_manager_journal')
        os.makedirs(os.path.dirname(self.journal_base))
        self.journal = StateJournal(self.journal_base)
        self.cruise_file = os.path.join(self.tmp, 'cruise.yaml')
        self.configs = read_config.expand_cruise_definition(
            read_config.read_config(self.cruise_file))['configs']

    def load(self, filename=None, loaded_time='2026-10-22T12:00:00.000Z', files=False):
        """Journal a definition load, as the logger manager would - with the
        hash of every file it is built from if files is true."""
        filename = filename or self.cruise_file
        extra = {}
        if files:
            extra['files'] = config_snapshot.definition_file_hashes(filename)
        self.journal.record('definition_loaded', cruise_id='TEST01', filename=filename,
                            loaded_time=loaded_time, file_sha256=sha256(filename), **extra)

    def served(self, config_name):
        """A config as the data stores give it to the logger manager: with
        its name added."""
        return {**self.configs[config_name], 'name': config_name}

    def start(self, logger, config_name, config=None):
        self.journal.record('logger_started', logger=logger, config=config_name,
                            config_sha256=config_hash(config or self.served(config_name)))

    def take(self):
        return self.snapshot(journal=self.journal_base)

    ############################
    def test_entries_since_load_and_current_state(self):
        # An earlier load of this file, and a load of another file, aren't
        # the one that counts
        self.load()
        self.start('gyro', 'gyro-off')
        other = self.write('other.yaml', 'cruise: {id: OTHER}\n')
        self.load(filename=other)

        self.journal.record('manager_start', host='test')
        self.load()
        self.journal.record('mode_changed', **{'from': None}, to='off')
        self.start('gyro', 'gyro-off')
        self.start('knud', 'knud-off')
        self.journal.record('mode_changed', **{'from': 'off'}, to='on')
        self.journal.record('config_changed', logger='gyro', **{'from': 'gyro-off'},
                            to='gyro-on', config_sha256=config_hash(self.served('gyro-on')))

        path, manifest = self.take()
        journal = manifest['journal']
        self.assertEqual(journal['entries'], 7)
        self.assertTrue(journal['definition_unchanged_since_load'])
        with open(os.path.join(path, journal['path'])) as f:
            events = [json.loads(line)['message_type'] for line in f]
        self.assertEqual(events, ['manager_start', 'definition_loaded', 'mode_changed',
                                  'logger_started',
                                  'logger_started', 'mode_changed', 'config_changed'])

        state = manifest['current_state']
        self.assertEqual(state['active_mode'], 'on')
        self.assertEqual({name: (s['config'], s['status'], s['matches_definition'])
                          for name, s in state['loggers'].items()},
                         {'gyro': ('gyro-on', 'running', True),
                          'knud': ('knud-off', 'running', True)})
        self.assertEqual(manifest['warnings'], [])
        # The load time comes from the journal
        self.assertEqual(manifest['snapshot']['cruise_definition_loaded'],
                         '2026-10-22T12:00:00Z')

    def test_configs_applied_just_before_the_load_is_recorded(self):
        """The logger manager journals a load after applying its configs, so
        the state is replayed from the manager's start, not the load."""
        self.journal.record('manager_start', host='test')
        self.journal.record('mode_changed', **{'from': None}, to='off')
        self.start('gyro', 'gyro-off')
        self.load()
        path, manifest = self.take()
        self.assertEqual(manifest['journal']['entries'], 4)
        self.assertEqual(manifest['current_state']['active_mode'], 'off')
        self.assertEqual(manifest['current_state']['loggers']['gyro']['config'], 'gyro-off')

    def test_bare_config_hash_also_matches(self):
        self.load()
        self.start('gyro', 'gyro-on', config=self.configs['gyro-on'])
        gyro = self.take()[1]['current_state']['loggers']['gyro']
        self.assertTrue(gyro['matches_definition'])

    def test_definition_changed_since_load(self):
        self.load()
        self.write('cruise.yaml', CRUISE.replace('<<tmp>>', self.tmp) + '# edited\n')
        path, manifest = self.take()
        self.assertFalse(manifest['journal']['definition_unchanged_since_load'])
        self.assertTrue(any('has changed since the logger manager loaded' in w
                            for w in manifest['warnings']))

    def test_running_config_differs_from_definition(self):
        self.load()
        self.start('gyro', 'gyro-on', config={'something': 'else'})
        path, manifest = self.take()
        self.assertFalse(manifest['current_state']['loggers']['gyro']['matches_definition'])
        self.assertTrue(any('differ from this definition: gyro' in w
                            for w in manifest['warnings']))

    def test_crashes_and_stops(self):
        self.load()
        self.start('gyro', 'gyro-on')
        self.start('knud', 'knud-off')
        self.journal.record('logger_crashed', logger='gyro', config='gyro-on', exit_code=1)
        self.journal.record('logger_failed', logger='gyro', config='gyro-on', crashes=3)
        loggers = self.take()[1]['current_state']['loggers']
        self.assertEqual((loggers['gyro']['status'], loggers['gyro']['crashes']), ('failed', 3))
        self.assertEqual(loggers['knud']['status'], 'running')

        self.journal.record('manager_stop', host='test')
        loggers = self.take()[1]['current_state']['loggers']
        self.assertEqual({s['status'] for s in loggers.values()}, {'stopped'})

    def test_recovery(self):
        self.load()
        self.start('gyro', 'gyro-on')
        self.journal.record('logger_crashed', logger='gyro', config='gyro-on', exit_code=1)
        self.assertEqual(self.take()[1]['current_state']['loggers']['gyro']['status'],
                         'crashing')
        self.journal.record('logger_recovered', logger='gyro', config='gyro-on', crashes=4)
        gyro = self.take()[1]['current_state']['loggers']['gyro']
        self.assertEqual((gyro['status'], gyro['crashes_before_recovery']), ('running', 4))

    def test_code_each_logger_was_started_with(self):
        self.load()
        self.journal.record('logger_started', logger='gyro', config='gyro-on',
                            config_sha256=config_hash(self.served('gyro-on')), code='v1')
        self.journal.record('logger_started', logger='knud', config='knud-off',
                            config_sha256=config_hash(self.served('knud-off')), code='v1')
        self.journal.record('logger_crashed', logger='gyro', config='gyro-on', code='v1')
        self.journal.record('logger_recovered', logger='gyro', config='gyro-on',
                            crashes=2, code='v2')
        loggers = self.take()[1]['current_state']['loggers']
        self.assertEqual({name: s['code'] for name, s in loggers.items()},
                         {'gyro': 'v2', 'knud': 'v1'})

    def test_definition_file_hashes(self):
        hashes = config_snapshot.definition_file_hashes(self.cruise_file)
        for rel in ('cruise.yaml', 'templates/gyro_template.yaml',
                    'devices/ship_devices.yaml', 'devices/types.yaml', 'header.txt'):
            path = os.path.join(self.tmp, rel)
            self.assertEqual(hashes[path], sha256(path))

    def test_exact_comparison_with_files_at_load(self):
        """With the hashes recorded at load time, a changed file is flagged
        even if its modification time is older than the load."""
        self.load(files=True, loaded_time='2099-01-01T00:00:00.000Z')
        types = self.write('devices/types.yaml', TYPES + '# edited\n')
        os.utime(types, (0, 0))   # an old modification time
        path, manifest = self.take()
        flags = {os.path.relpath(f['source'], self.tmp): f['modified_after_load']
                 for f in manifest['files'] if f['source'].startswith(self.tmp)}
        self.assertTrue(flags['devices/types.yaml'])
        self.assertFalse(flags['cruise.yaml'])
        self.assertEqual(manifest['journal']['files_added_since_load'], [])
        self.assertEqual(manifest['journal']['files_removed_since_load'], [])

    def test_files_added_and_removed_since_load(self):
        self.load(files=True)
        # The device file now includes a different file than at load time
        self.write('devices/more_types.yaml', TYPES.replace('Gyro', 'Gyro2'))
        self.write('devices/ship_devices.yaml',
                   DEVICES.replace('<<tmp>>', self.tmp).replace('types.yaml', 'more_types.yaml'))
        path, manifest = self.take()
        journal = manifest['journal']
        self.assertEqual(journal['files_added_since_load'],
                         [os.path.join(self.tmp, 'devices/more_types.yaml')])
        self.assertEqual(journal['files_removed_since_load'],
                         [os.path.join(self.tmp, 'devices/types.yaml')])
        self.assertTrue(any('Files added since' in w for w in manifest['warnings']))
        self.assertTrue(any('Files removed since' in w for w in manifest['warnings']))

    def test_snapshot_of_what_is_running(self):
        """With no cruise file given, snapshot the one last loaded."""
        other = self.write('other.yaml', CRUISE.replace('<<tmp>>', self.tmp)
                           .replace('TEST01', 'OTHER'))
        self.load(filename=other)
        self.load()
        path = config_snapshot.take_snapshot(output_dir=self.output, journal=self.journal_base)
        with open(os.path.join(path, 'MANIFEST.yaml')) as f:
            manifest = yaml.safe_load(f)
        self.assertEqual(manifest['snapshot']['cruise_definition'], self.cruise_file)

        output = io.StringIO()
        with redirect_stdout(output):
            config_snapshot.main(['--output', self.output, '--journal', self.journal_base])
        self.assertTrue(os.path.isfile(os.path.join(output.getvalue().strip(), 'MANIFEST.yaml')))

    def test_nothing_running_and_no_file_given(self):
        with self.assertRaises(ValueError):
            config_snapshot.take_snapshot(output_dir=self.output, journal=self.journal_base)

    def test_journal_missing_or_not_recording_this_definition(self):
        path, manifest = self.take()
        self.assertIsNone(manifest['journal'])
        self.assertTrue(any('No logger manager journal found' in w
                            for w in manifest['warnings']))

        self.load(filename=self.write('other.yaml', 'cruise: {id: OTHER}\n'))
        path, manifest = self.take()
        self.assertIsNone(manifest['current_state'])
        self.assertTrue(any('does not record loading' in w for w in manifest['warnings']))
        self.assertFalse(os.path.exists(os.path.join(path, 'logger_manager_journal.jsonl')))


@unittest.skipUnless(shutil.which('git'), 'git not available')
class TestCodeVersion(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = self.temp_dir.name
        self.git('init', '-q')
        self.write('module.py', 'x = 1\n')
        self.git('add', 'module.py')
        self.git('-c', 'user.name=test', '-c', 'user.email=test@example.com',
                 'commit', '-q', '-m', 'first')

    def git(self, *args):
        subprocess.run(['git'] + list(args), cwd=self.repo, check=True,
                       capture_output=True)

    def write(self, name, content):
        with open(os.path.join(self.repo, name), 'w') as f:
            f.write(content)

    def test_clean_tree_is_its_commit(self):
        version = config_snapshot.code_version(self.repo)
        self.assertRegex(version, r'^[0-9a-f]{7,}$')
        self.write('notes.txt', 'not code\n')   # untracked non-code: no difference
        self.assertEqual(config_snapshot.code_version(self.repo), version)

    def test_different_changes_give_different_versions(self):
        clean = config_snapshot.code_version(self.repo)
        self.write('module.py', 'x = 2\n')
        edit_1 = config_snapshot.code_version(self.repo)
        self.assertRegex(edit_1, '^' + clean + r'-dirty\.[0-9a-f]{12}$')
        self.assertEqual(config_snapshot.code_version(self.repo), edit_1)  # repeatable
        self.write('module.py', 'x = 3\n')
        self.assertNotEqual(config_snapshot.code_version(self.repo), edit_1)
        self.write('module.py', 'x = 1\n')
        self.assertEqual(config_snapshot.code_version(self.repo), clean)

    def test_untracked_code_counts(self):
        clean = config_snapshot.code_version(self.repo)
        self.write('new_reader.py', 'y = 1\n')
        new_1 = config_snapshot.code_version(self.repo)
        self.assertTrue(new_1.startswith(clean + '-dirty.'))
        self.write('new_reader.py', 'y = 2\n')
        self.assertNotEqual(config_snapshot.code_version(self.repo), new_1)

    def test_not_a_repository(self):
        shutil.rmtree(os.path.join(self.repo, '.git'))
        self.assertIsNone(config_snapshot.code_version(self.repo))

    def test_snapshot_records_it(self):
        info, statuses, diff = config_snapshot.repository_info(self.repo, [])
        self.assertEqual(info['code_version'], config_snapshot.code_version(self.repo))


class TestFilesRead(unittest.TestCase):
    """read_config's files_read hook, which the snapshot is built on."""

    def test_records_files_actually_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            a_yaml = ('includes_base_dir: %s\n'
                      'includes: [b.yaml, missing.yaml]\n'
                      'x: 1\n' % tmp)
            for name, content in (('a.yaml', a_yaml), ('b.yaml', 'y: 2\n')):
                with open(os.path.join(tmp, name), 'w') as f:
                    f.write(content)
            files_read = []
            logging.disable(logging.CRITICAL)
            try:
                definition = read_config.read_config(os.path.join(tmp, 'a.yaml'),
                                                     files_read=files_read)
                read_config.expand_includes(definition, files_read=files_read)
            finally:
                logging.disable(logging.NOTSET)
            self.assertEqual(files_read, [os.path.join(tmp, 'a.yaml'),
                                          os.path.join(tmp, 'b.yaml')])


if __name__ == '__main__':
    unittest.main()
