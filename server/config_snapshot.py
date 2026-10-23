#!/usr/bin/env python3
"""Capture a snapshot of everything that determines how a cruise's data were
acquired and processed, so that the data can be understood later and the
processing reproduced: the cruise definition, every file it was built from,
the device definitions its parsers use, the version of the code, and the
environment it ran in. See issue #413.

Usage:

    config_snapshot test/NBP1406/NBP1406_cruise.yaml --output /var/data/snapshots
    config_snapshot my_cruise.yaml --tar

which writes a directory (and, with --tar, a .tar.gz of it) named
<cruise id>_<UTC time>, containing:

    MANIFEST.yaml          when and where the snapshot was taken; the OpenRVDAS
                           version; git commit, branch, tag and remote of each
                           repository a file came from, and whether it had
                           uncommitted changes, and its code version (see
                           code_version()); the OS, Python and installed
                           packages; and every captured file with its sha256,
                           size, modification time and git status, and - if it
                           was reached through a symlink - the file it
                           resolves to
    expanded_config.yaml   the fully expanded cruise definition, as the logger
                           manager sees it, with passwords, tokens and other
                           secrets redacted
    sources/               every file captured, at its path relative to the
                           OpenRVDAS directory (files outside it go under
                           sources/_abs/), so the tree can be loaded again
    patches/               for each repository with uncommitted changes, the
                           output of "git diff HEAD"
    logger_manager_journal.jsonl
                           the logger manager's journal entries (issue #670)
                           from its last start before this cruise definition
                           was loaded: every mode change, config change,
                           logger start, stop, crash and recovery since then

From the journal, the manifest also records:

  - whether the definition the logger manager loaded is the one being
    snapshotted, by comparing the sha256 the journal recorded for it at load
    time with the file's sha256 now;
  - the current state: the active mode, and each logger's config, whether it
    is running, crashing or failed, and whether the config it is running is
    identical to the one in this definition (by comparing config hashes),
    and the code version it was started with - which may differ from the
    repository's now, if the code has changed since.

Files captured are the cruise definition; every file it includes; the device
definition files named by any ParseTransform or RegexParseTransform (or the
defaults a ParseTransform uses if it names none), and the files they include;
and any LogfileWriter header files.

Source files are copied exactly, so they can be reloaded. If any of them
appears to contain a password, token or similar, the manifest lists where,
and a warning is printed, so the snapshot can be handled accordingly.
"""
import argparse
import copy
import datetime
import glob
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tarfile

import yaml

from logger.utils import read_config  # noqa: E402
from server.state_journal import config_hash  # noqa: E402

OPENRVDAS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Default definition path for a ParseTransform that doesn't name one. Kept as
# a string rather than imported, so that taking a snapshot doesn't depend on
# importing the parser. Must match record_parser.DEFAULT_DEFINITION_PATH.
DEFAULT_DEFINITION_PATH = 'logger/devices/*.yaml,contrib/devices/*.yaml'

# Transforms that read device definitions, and whether they have a default.
PARSER_CLASSES = {
    'ParseTransform': DEFAULT_DEFINITION_PATH,
    'RegexParseTransform': None,
}

# Names that suggest a value is a secret. Matched against config keys, and
# against keys in source files.
SECRET_PATTERN = r'(password|passwd|secret|token|api_?key|credential)'
SECRET_KEY = re.compile(SECRET_PATTERN, re.IGNORECASE)
SECRET_LINE = re.compile(r'^\s*-?\s*["\']?[\w.-]*' + SECRET_PATTERN +
                         r'[\w.-]*["\']?\s*:\s*\S', re.IGNORECASE)
REDACTED = '<redacted>'

TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

# Where the logger manager writes its journal by default; must match
# DEFAULT_STATE_JOURNAL in server/logger_manager.py, which isn't imported so
# that taking a snapshot doesn't import the logger manager.
DEFAULT_JOURNAL = '/var/log/openrvdas/logger_manager_journal'
JOURNAL_FILE = 'logger_manager_journal.jsonl'


################################################################################
def _utc_iso(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).strftime(TIME_FORMAT)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 16), b''):
            digest.update(block)
    return digest.hexdigest()


def _git(args, cwd):
    """Run git; return its stripped output, or None if it fails."""
    try:
        return subprocess.run(['git'] + args, cwd=cwd, capture_output=True,
                              text=True, check=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def code_version(repo_root=OPENRVDAS_ROOT):
    """A short string identifying the exact code in a git working tree: its
    'git describe', plus - if it differs from that commit - a hash of the
    differences, e.g. v2.6.3.dev0-12-g2c1a06f5-dirty.3fa94c1e02ab. The hash
    covers uncommitted changes and untracked Python files (which 'git
    describe --dirty' ignores), so two different sets of local edits give
    two different versions. Returns None if repo_root isn't in a git
    repository or git isn't available.

    The logger manager records this in its journal each time it starts a
    logger, and a snapshot records it for the repository, so the two can be
    compared."""
    describe = _git(['describe', '--tags', '--always'], repo_root)
    if describe is None:
        return None
    digest = hashlib.sha256()
    diff = _git(['diff', 'HEAD'], repo_root) or ''
    digest.update(diff.encode('utf-8'))
    untracked = _git(['ls-files', '--others', '--exclude-standard', '--', '*.py'],
                     repo_root) or ''
    for rel in sorted(untracked.splitlines()):
        digest.update(b'\0' + rel.encode('utf-8') + b'\0')
        try:
            with open(os.path.join(repo_root, rel), 'rb') as f:
                digest.update(f.read())
        except OSError:
            pass
    if not diff and not untracked:
        return describe
    return f'{describe}-dirty.{digest.hexdigest()[:12]}'


################################################################################
def find_definition_files(configs, files_read, errors):
    """Find the device definition files and header files that the logger
    configs in an expanded cruise definition refer to, appending each file
    read to files_read."""
    def visit(node):
        if isinstance(node, dict):
            kwargs = node.get('kwargs') if isinstance(node.get('kwargs'), dict) else {}
            if node.get('class') in PARSER_CLASSES:
                definition_path = kwargs.get('definition_path',
                                             PARSER_CLASSES[node['class']])
                if definition_path:
                    _read_definitions(definition_path, files_read, errors)
            header_file = kwargs.get('header_file') if node.get('class') else None
            if isinstance(header_file, str):
                header_file = [header_file]
            elif isinstance(header_file, dict):
                header_file = list(header_file.values())
            for path in header_file or []:
                path = _resolve(path)
                if os.path.isfile(path):
                    files_read.append(path)
                else:
                    errors.append(f'Header file not found: "{path}"')
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(configs)


def _resolve(path):
    """Loggers run with the OpenRVDAS directory as their working directory,
    so resolve relative paths against it, whatever ours is."""
    return path if os.path.isabs(path) else os.path.join(OPENRVDAS_ROOT, path)


def _read_definitions(definition_path, files_read, errors):
    globs = [_resolve(g.strip()) for g in definition_path.split(',') if g.strip()]
    for pattern in globs:
        if not glob.glob(pattern):
            errors.append(f'No device definition files match "{pattern}"')
    read_config.load_definitions(','.join(globs), files_read=files_read)


################################################################################
def definition_files(cruise_file):
    """Load and expand a cruise definition, recording every file it is built
    from. Returns (expanded definition, list of absolute paths in the order
    first read, list of problems found). Raises ValueError if the definition
    itself can't be read."""
    errors, files_read = [], []
    definition = read_config.read_config(cruise_file, errors=errors, files_read=files_read)
    if errors:
        raise ValueError(f'Could not read cruise definition: {"; ".join(errors)}')
    expanded = read_config.expand_cruise_definition(definition, errors=errors,
                                                    files_read=files_read)
    find_definition_files(expanded.get('configs', {}), files_read, errors)
    return expanded, list(dict.fromkeys(files_read)), errors


def definition_file_hashes(cruise_file):
    """{absolute path: sha256} for every file a cruise definition is built
    from. The logger manager records this when it loads a definition, so a
    later snapshot can tell exactly which files have changed since."""
    _, paths, _ = definition_files(_resolve(cruise_file))
    hashes = {}
    for path in paths:
        try:
            hashes[path] = _sha256(path)
        except OSError:
            hashes[path] = None
    return hashes


################################################################################
def redact(node):
    """Return a copy of node with the values of secret-looking keys replaced."""
    if isinstance(node, dict):
        return {key: (REDACTED if isinstance(key, str) and SECRET_KEY.search(key)
                      and value not in (None, '') else redact(value))
                for key, value in node.items()}
    if isinstance(node, list):
        return [redact(value) for value in node]
    return node


def find_secret_lines(path):
    """Line numbers in a text file that look like they set a secret."""
    try:
        with open(path, errors='replace') as f:
            return [n for n, line in enumerate(f, 1) if SECRET_LINE.search(line)]
    except OSError:
        return []


################################################################################
def repository_info(repo_root, captured_paths):
    """git state of a repository, and the git status of each captured file in
    it. Returns (info, statuses, diff)."""
    info = {
        'root': repo_root,
        'commit': _git(['rev-parse', 'HEAD'], repo_root),
        'branch': _git(['rev-parse', '--abbrev-ref', 'HEAD'], repo_root),
        'describe': _git(['describe', '--tags', '--always', '--dirty'], repo_root),
        'remote': (_git(['remote', 'get-url', 'origin'], repo_root)
                   or None),
        # Comparable with the 'code' the logger manager journals for each logger
        'code_version': code_version(repo_root),
    }
    if info['branch'] == 'HEAD':
        info['branch'] = None  # detached

    diff = _git(['diff', 'HEAD'], repo_root) or ''
    info['uncommitted_changes'] = bool(diff)

    # Status of each captured file: clean, modified, untracked or ignored.
    statuses = {}
    porcelain = _git(['status', '--porcelain', '--untracked-files=all', '--ignored'],
                     repo_root) or ''
    by_path = {}
    for line in porcelain.splitlines():
        code, rel = line[:2], line[3:]
        by_path[rel.split(' -> ')[-1]] = code

    # "git diff HEAD" doesn't show new files that haven't been added to git,
    # so list untracked Python files: new code that is in use would otherwise
    # leave no trace in the snapshot. (Only code, so that stray files in a
    # working tree aren't listed in a manifest that travels with the data.)
    info['untracked_code'] = sorted(rel for rel, code in by_path.items()
                                    if code == '??' and rel.endswith('.py'))
    for path in captured_paths:
        rel = os.path.relpath(os.path.realpath(path), repo_root)
        code = by_path.get(rel)
        statuses[path] = ('clean' if code is None else
                          'untracked' if code == '??' else
                          'ignored' if code == '!!' else 'modified')
    return info, statuses, diff


def environment_info():
    """Where and on what the snapshot was taken."""
    try:
        from logger.utils.read_version import get_version
        version = get_version()
    except Exception as e:  # noqa: BLE001 - a snapshot must not fail for this
        version = f'unknown ({type(e).__name__}: {e})'

    packages = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get('Name')
        if name:
            packages[name] = dist.version
    return {
        'openrvdas_version': version,
        'openrvdas_root': OPENRVDAS_ROOT,
        'hostname': socket.gethostname(),
        'user': os.environ.get('USER') or os.environ.get('USERNAME'),
        'os': platform.platform(),
        'python': sys.version.split()[0],
        'python_executable': sys.executable,
        'packages': dict(sorted(packages.items(), key=lambda kv: kv[0].lower())),
    }


################################################################################
def read_journal(filebase):
    """Read the logger manager's journal: a list of (line, record dict), in
    order. Lines that aren't JSON are skipped."""
    entries = []
    for path in sorted(glob.glob(filebase + '-*')):
        with open(path, errors='replace') as f:
            for line in f:
                line = line.rstrip('\n')
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict) and isinstance(record.get('fields'), dict):
                    entries.append((line, record))
    entries.sort(key=lambda entry: entry[1].get('timestamp') or 0)
    return entries


def _same_file(journal_filename, cruise_file):
    """Is the file the journal says was loaded the one we're snapshotting?
    The logger manager may have been given a relative path; it runs in the
    OpenRVDAS directory, so resolve against that."""
    if not journal_filename:
        return False
    return os.path.realpath(_resolve(journal_filename)) == os.path.realpath(cruise_file)


def last_load(entries, cruise_file=None):
    """Index of the latest definition_loaded entry for this cruise file (or
    for any file, if cruise_file is None), or None if the journal doesn't
    record it being loaded."""
    for index in range(len(entries) - 1, -1, -1):
        record = entries[index][1]
        if record.get('message_type') == 'definition_loaded' and (
                cruise_file is None or
                _same_file(record['fields'].get('filename'), cruise_file)):
            return index
    return None


def last_loaded_file(journal):
    """The cruise definition file the logger manager most recently loaded,
    according to its journal, or None."""
    entries = read_journal(journal) if journal else []
    index = last_load(entries)
    if index is None:
        return None
    filename = entries[index][1]['fields'].get('filename')
    return _resolve(filename) if filename else None


def run_start(entries, load_index):
    """Index of the logger manager's start preceding the load at load_index
    (or 0 if the journal doesn't go back that far).

    State has to be replayed from here rather than from the load itself:
    the logger manager applies a newly loaded definition's configs - mode
    change, loggers started - just before it records definition_loaded, and
    the state is cumulative in any case."""
    for index in range(load_index, -1, -1):
        if entries[index][1].get('message_type') == 'manager_start':
            return index
    return 0


def _config_matches(config, config_name, journal_sha256):
    """Is the config the logger manager ran (as hashed in the journal) this
    definition's config? The data stores add the config's name to each
    config when it is loaded - so that is what the logger manager hashes -
    but accept the bare config too, in case a store doesn't."""
    if config is None or not journal_sha256:
        return False
    return journal_sha256 in (config_hash({**config, 'name': config_name}),
                              config_hash(config))


def current_state(records, configs):
    """Replay journal records to find the active mode and each logger's
    state, and check each running config against this definition's."""
    mode = None
    loggers = {}
    for record in records:
        event, fields = record.get('message_type'), record['fields']
        logger = fields.get('logger')
        if event == 'mode_changed':
            mode = fields.get('to')
        elif event in ('logger_started', 'config_changed'):
            loggers[logger] = {'config': fields.get('config') or fields.get('to'),
                               'config_sha256': fields.get('config_sha256'),
                               'code': fields.get('code'),
                               'status': 'running', 'since': fields.get('time')}
        elif event == 'logger_stopped' and logger in loggers:
            loggers[logger].update(status='stopped', since=fields.get('time'))
        elif event == 'logger_crashed' and logger in loggers:
            loggers[logger].update(status='crashing', since=fields.get('time'))
        elif event == 'logger_recovered' and logger in loggers:
            loggers[logger].update(status='running', since=fields.get('time'),
                                   code=fields.get('code', loggers[logger]['code']),
                                   crashes_before_recovery=fields.get('crashes'))
        elif event == 'logger_failed' and logger in loggers:
            loggers[logger].update(status='failed', since=fields.get('time'),
                                   crashes=fields.get('crashes'))
        elif event == 'manager_stop':
            for state in loggers.values():
                state.update(status='stopped', since=fields.get('time'))

    for state in loggers.values():
        state['matches_definition'] = _config_matches(
            configs.get(state['config']), state['config'], state['config_sha256'])
    return {'as_of': records[-1]['fields'].get('time') if records else None,
            'active_mode': mode,
            'loggers': dict(sorted(loggers.items()))}


################################################################################
def take_snapshot(cruise_file=None, output_dir='.', make_tar=False, redact_secrets=True,
                  loaded_time=None, journal=DEFAULT_JOURNAL):
    """Snapshot a cruise definition and everything it depends on.

    cruise_file     Path of the cruise definition file. If None, the file the
                    logger manager most recently loaded, according to its
                    journal - i.e. a snapshot of what is running now.
    output_dir      Directory in which to create the snapshot directory.
    make_tar        Also write <snapshot>.tar.gz next to the directory.
    redact_secrets  Redact secret-looking values in expanded_config.yaml.
    loaded_time     Optional datetime (UTC) when the definition was loaded
                    into the logger manager. Any captured file modified after
                    it is flagged, since the snapshot may then differ from
                    what is actually running. If not given, taken from the
                    logger manager's journal, if it records loading this file.
    journal         Path prefix of the logger manager's journal files
                    (--state_journal), or None not to look for them.

    Returns the path of the snapshot directory (or of the .tar.gz, if
    make_tar is set).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    if cruise_file is None:
        cruise_file = last_loaded_file(journal)
        if cruise_file is None:
            raise ValueError('No cruise definition given, and no logger manager '
                             f'journal at {journal} records loading one')
    cruise_file = os.path.abspath(cruise_file)

    # Load and expand the definition, recording every file it is built from.
    expanded, captured, errors = definition_files(cruise_file)

    cruise_id = str((expanded.get('cruise') or {}).get('id') or
                    os.path.splitext(os.path.basename(cruise_file))[0])

    # The logger manager's journal, from when it last loaded this definition.
    journal_info, journal_lines, state, hashes_at_load = None, [], None, None
    entries = read_journal(journal) if journal else []
    if journal and not entries:
        errors.append(f'No logger manager journal found at {journal}-*')
    elif entries:
        start = last_load(entries, cruise_file)
        if start is None:
            errors.append(f'The logger manager journal at {journal} does not record '
                          f'loading {cruise_file}, so the current state is unknown')
        else:
            loaded = entries[start][1]['fields']
            start = run_start(entries, start)
            file_sha256 = _sha256(cruise_file)
            journal_lines = [line for line, _ in entries[start:]]
            journal_info = {
                'source': journal,
                'path': JOURNAL_FILE,
                'entries': len(journal_lines),
                'since': entries[start][1]['fields'].get('time'),
                'definition_loaded': loaded.get('loaded_time'),
                'definition_sha256_at_load': loaded.get('file_sha256'),
                'definition_unchanged_since_load': loaded.get('file_sha256') == file_sha256,
            }
            if not journal_info['definition_unchanged_since_load']:
                errors.append(f'{cruise_file} has changed since the logger manager loaded '
                              f'it, so what is running may not match this snapshot')
            state = current_state([record for _, record in entries[start:]],
                                  expanded.get('configs', {}))
            mismatched = [name for name, s in state['loggers'].items()
                          if not s['matches_definition'] and s['status'] != 'stopped']
            if mismatched:
                errors.append('These loggers are running configs that differ from this '
                              f'definition: {", ".join(mismatched)}')
            # Which files have changed since the definition was loaded: exact,
            # if the logger manager recorded each file's hash at load time.
            hashes_at_load = loaded.get('files')
            if isinstance(hashes_at_load, dict):
                journal_info['files_added_since_load'] = sorted(
                    set(captured) - set(hashes_at_load))
                journal_info['files_removed_since_load'] = sorted(
                    set(hashes_at_load) - set(captured))
                for kind in ('added', 'removed'):
                    if journal_info[f'files_{kind}_since_load']:
                        errors.append(f'Files {kind} since the definition was loaded: '
                                      + ', '.join(journal_info[f'files_{kind}_since_load']))
            else:
                hashes_at_load = None
            if loaded_time is None and loaded.get('loaded_time'):
                try:
                    loaded_time = datetime.datetime.strptime(
                        loaded['loaded_time'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(
                            tzinfo=datetime.timezone.utc)
                except ValueError:
                    pass

    base_name = re.sub(r'[^\w.-]+', '_', cruise_id) + '_' + now.strftime('%Y%m%dT%H%M%SZ')
    # Two snapshots in the same second get _2, _3... rather than colliding.
    name, count = base_name, 1
    while os.path.exists(os.path.join(output_dir, name)) or \
            os.path.exists(os.path.join(output_dir, name + '.tar.gz')):
        count += 1
        name = f'{base_name}_{count}'
    snapshot_dir = os.path.join(output_dir, name)
    os.makedirs(snapshot_dir)

    # Copy the files, keeping paths relative to the OpenRVDAS directory.
    files = []
    for path in captured:
        rel = os.path.relpath(path, OPENRVDAS_ROOT)
        archive_path = (os.path.join('sources', rel) if not rel.startswith('..')
                        else os.path.join('sources', '_abs', path.lstrip(os.sep)))
        dest = os.path.join(snapshot_dir, archive_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(path, dest)
        stat = os.stat(path)
        entry = {'path': archive_path, 'source': path, 'sha256': _sha256(path),
                 'size': stat.st_size, 'modified': _utc_iso(stat.st_mtime)}
        # Reached through a symlink - such as a calibrations.yaml link to the
        # current dated file, or a local/ linked to another repository? Then
        # record what it really is, which the contents alone don't say.
        real_path = os.path.realpath(path)
        if real_path != os.path.abspath(path):
            entry['resolves_to'] = real_path
        if hashes_at_load is not None:
            # Exact: compare with the hash recorded when it was loaded
            entry['modified_after_load'] = (path in hashes_at_load and
                                            hashes_at_load[path] != entry['sha256'])
        elif loaded_time is not None:
            # Approximate: by modification time, which git operations change too
            entry['modified_after_load'] = stat.st_mtime > loaded_time.timestamp()
        secret_lines = find_secret_lines(path)
        if secret_lines:
            entry['possible_secrets_on_lines'] = secret_lines
        files.append(entry)

    # The state of each git repository the files came from.
    repos = {}
    for entry in files:
        top = _git(['rev-parse', '--show-toplevel'],
                   os.path.dirname(os.path.realpath(entry['source'])))
        repos.setdefault(top, []).append(entry['source'])
    repositories = []
    for top, paths in repos.items():
        if top is None:
            for entry in files:
                if entry['source'] in paths:
                    entry['git'] = 'not in a git repository'
            continue
        info, statuses, diff = repository_info(top, paths)
        if diff:
            patch_name = re.sub(r'[^\w.-]+', '_', top.strip(os.sep)) + '.diff'
            os.makedirs(os.path.join(snapshot_dir, 'patches'), exist_ok=True)
            with open(os.path.join(snapshot_dir, 'patches', patch_name), 'w') as f:
                f.write(diff + '\n')
            info['patch'] = os.path.join('patches', patch_name)
        for entry in files:
            if entry['source'] in statuses:
                entry['git'] = statuses[entry['source']]
        repositories.append(info)

    # The expanded definition, as the logger manager sees it.
    with open(os.path.join(snapshot_dir, 'expanded_config.yaml'), 'w') as f:
        yaml.safe_dump(redact(copy.deepcopy(expanded)) if redact_secrets else expanded,
                       f, sort_keys=False, default_flow_style=False)

    if journal_lines:
        with open(os.path.join(snapshot_dir, JOURNAL_FILE), 'w') as f:
            f.write('\n'.join(journal_lines) + '\n')

    manifest = {
        'snapshot': {
            'taken': now.strftime(TIME_FORMAT),
            'cruise_id': cruise_id,
            'cruise_definition': cruise_file,
            'cruise_definition_loaded': (loaded_time.strftime(TIME_FORMAT)
                                         if loaded_time else None),
            'expanded_definition': 'expanded_config.yaml',
            'secrets_redacted': redact_secrets,
        },
        'environment': environment_info(),
        'repositories': repositories,
        'files': files,
        'journal': journal_info,
        'current_state': state,
        'warnings': errors,
    }
    with open(os.path.join(snapshot_dir, 'MANIFEST.yaml'), 'w') as f:
        yaml.safe_dump(manifest, f, sort_keys=False, default_flow_style=False)

    # Only the files' paths are logged; MANIFEST.yaml gives the line numbers.
    files_with_possible_secrets = [e['path'] for e in files
                                   if e.get('possible_secrets_on_lines')]
    if files_with_possible_secrets:
        logging.warning('These captured files may contain passwords or tokens, '
                        'copied as-is: %s. See MANIFEST.yaml.',
                        ', '.join(files_with_possible_secrets))
    changed = [e['path'] for e in files if e.get('modified_after_load')]
    if changed:
        logging.warning('These files have changed since the definition was '
                        'loaded, so may not match what is running: %s', ', '.join(changed))
    for error in errors:
        logging.warning(error)

    if not make_tar:
        return snapshot_dir
    tar_path = snapshot_dir + '.tar.gz'
    with tarfile.open(tar_path, 'w:gz') as tar:
        tar.add(snapshot_dir, arcname=name)
    return tar_path


################################################################################
def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Snapshot a cruise definition, every file it was built '
        'from, the device definitions it uses, the code version and the '
        'environment, so that data can be traced back to how they were '
        'acquired and processed.')
    parser.add_argument('cruise_file', nargs='?', default=None,
                        help='Cruise definition file. If omitted, the one the '
                        'logger manager most recently loaded, according to its '
                        'journal: a snapshot of what is running now.')
    parser.add_argument('--output', default='.',
                        help='Directory to write the snapshot in (default: .)')
    parser.add_argument('--tar', action='store_true',
                        help='Also write the snapshot as a .tar.gz')
    parser.add_argument('--no-redact', dest='redact', action='store_false',
                        help='Don\'t redact secrets in expanded_config.yaml')
    parser.add_argument('--journal', default=DEFAULT_JOURNAL,
                        help='Path prefix of the logger manager\'s journal files '
                        f'(default: {DEFAULT_JOURNAL}); "none" not to use one')
    parser.add_argument('--loaded-time',
                        help='When the definition was loaded, as UTC '
                        'YYYY-MM-DDTHH:MM:SSZ; files modified since are flagged')
    args = parser.parse_args(argv)
    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.WARNING)

    loaded_time = None
    if args.loaded_time:
        loaded_time = datetime.datetime.strptime(args.loaded_time, TIME_FORMAT).replace(
            tzinfo=datetime.timezone.utc)
    journal = None if args.journal.lower() == 'none' else args.journal
    print(take_snapshot(args.cruise_file, output_dir=args.output, make_tar=args.tar,
                        redact_secrets=args.redact, loaded_time=loaded_time,
                        journal=journal))


if __name__ == '__main__':
    main()
