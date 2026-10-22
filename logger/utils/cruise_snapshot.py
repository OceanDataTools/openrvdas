#!/usr/bin/env python3
"""Capture a snapshot of everything that determines how a cruise's data were
acquired and processed, so that the data can be understood later and the
processing reproduced: the cruise definition, every file it was built from,
the device definitions its parsers use, the version of the code, and the
environment it ran in. See issue #413.

Usage:

    cruise_snapshot test/NBP1406/NBP1406_cruise.yaml --output /var/data/snapshots
    cruise_snapshot my_cruise.yaml --tar

which writes a directory (and, with --tar, a .tar.gz of it) named
<cruise id>_<UTC time>, containing:

    MANIFEST.yaml          when and where the snapshot was taken; the OpenRVDAS
                           version; git commit, branch, tag and remote of each
                           repository a file came from, and whether it had
                           uncommitted changes; the OS, Python and installed
                           packages; and every captured file with its sha256,
                           size, modification time and git status
    expanded_cruise.yaml   the fully expanded cruise definition, as the logger
                           manager sees it, with passwords, tokens and other
                           secrets redacted
    sources/               every file captured, at its path relative to the
                           OpenRVDAS directory (files outside it go under
                           sources/_abs/), so the tree can be loaded again
    patches/               for each repository with uncommitted changes, the
                           output of "git diff HEAD"

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

OPENRVDAS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
def take_snapshot(cruise_file, output_dir='.', make_tar=False, redact_secrets=True,
                  loaded_time=None):
    """Snapshot a cruise definition and everything it depends on.

    cruise_file     Path of the cruise definition file.
    output_dir      Directory in which to create the snapshot directory.
    make_tar        Also write <snapshot>.tar.gz next to the directory.
    redact_secrets  Redact secret-looking values in expanded_cruise.yaml.
    loaded_time     Optional datetime (UTC) when the definition was loaded
                    into the logger manager. Any captured file modified after
                    it is flagged, since the snapshot may then differ from
                    what is actually running.

    Returns the path of the snapshot directory (or of the .tar.gz, if
    make_tar is set).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    cruise_file = os.path.abspath(cruise_file)

    # Load and expand the definition, recording every file read.
    errors, files_read = [], []
    definition = read_config.read_config(cruise_file, errors=errors, files_read=files_read)
    if errors:
        raise ValueError(f'Could not read cruise definition: {"; ".join(errors)}')
    expanded = read_config.expand_cruise_definition(definition, errors=errors,
                                                    files_read=files_read)
    find_definition_files(expanded.get('configs', {}), files_read, errors)

    # Unique files, in the order first read
    captured = list(dict.fromkeys(files_read))

    cruise_id = str((expanded.get('cruise') or {}).get('id') or
                    os.path.splitext(os.path.basename(cruise_file))[0])
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
        if loaded_time is not None:
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
    with open(os.path.join(snapshot_dir, 'expanded_cruise.yaml'), 'w') as f:
        yaml.safe_dump(redact(copy.deepcopy(expanded)) if redact_secrets else expanded,
                       f, sort_keys=False, default_flow_style=False)

    manifest = {
        'snapshot': {
            'taken': now.strftime(TIME_FORMAT),
            'cruise_id': cruise_id,
            'cruise_definition': cruise_file,
            'cruise_definition_loaded': (loaded_time.strftime(TIME_FORMAT)
                                         if loaded_time else None),
            'expanded_definition': 'expanded_cruise.yaml',
            'secrets_redacted': redact_secrets,
        },
        'environment': environment_info(),
        'repositories': repositories,
        'files': files,
        'warnings': errors,
    }
    with open(os.path.join(snapshot_dir, 'MANIFEST.yaml'), 'w') as f:
        yaml.safe_dump(manifest, f, sort_keys=False, default_flow_style=False)

    secrets = [e['path'] for e in files if e.get('possible_secrets_on_lines')]
    if secrets:
        logging.warning('These captured files may contain passwords or tokens, '
                        'copied as-is: %s. See MANIFEST.yaml.', ', '.join(secrets))
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
    parser.add_argument('cruise_file', help='Cruise definition file')
    parser.add_argument('--output', default='.',
                        help='Directory to write the snapshot in (default: .)')
    parser.add_argument('--tar', action='store_true',
                        help='Also write the snapshot as a .tar.gz')
    parser.add_argument('--no-redact', dest='redact', action='store_false',
                        help='Don\'t redact secrets in expanded_cruise.yaml')
    parser.add_argument('--loaded-time',
                        help='When the definition was loaded, as UTC '
                        'YYYY-MM-DDTHH:MM:SSZ; files modified since are flagged')
    args = parser.parse_args(argv)
    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.WARNING)

    loaded_time = None
    if args.loaded_time:
        loaded_time = datetime.datetime.strptime(args.loaded_time, TIME_FORMAT).replace(
            tzinfo=datetime.timezone.utc)
    print(take_snapshot(args.cruise_file, output_dir=args.output, make_tar=args.tar,
                        redact_secrets=args.redact, loaded_time=loaded_time))


if __name__ == '__main__':
    main()
