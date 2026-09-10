#!/usr/bin/env python3
"""Utility for reading the OpenRVDAS release version from pyproject.toml.
"""
import logging
import os
import re

# pyproject.toml lives at the repo root, two levels up from this file:
# logger/utils/read_version.py -> logger/utils -> logger -> repo root.
PYPROJECT_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'pyproject.toml')

# Matches the top-level "version = "..."" line under [project]. Anchored to
# the start of a line so it doesn't match inline dependency version
# constraints (e.g. 'fastapi = {version = "^0.135.0"}').
VERSION_RE = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"', re.MULTILINE)


###############################################################################
def get_version(pyproject_path: str = PYPROJECT_PATH) -> str:
    """
    Read the OpenRVDAS release version out of pyproject.toml.

    Uses a simple regex rather than a TOML parser so this works on the
    project's full supported Python range (the stdlib "tomllib" module
    requires Python 3.11+) without adding a new third-party dependency.

    Args:
        pyproject_path: Path to pyproject.toml (defaults to the repo root's)

    Returns:
        The version string, or "unknown" if it can't be determined
    """
    try:
        with open(pyproject_path, 'r') as f:
            contents = f.read()
    except OSError as e:
        logging.warning('Could not read %s: %s', pyproject_path, e)
        return 'unknown'

    match = VERSION_RE.search(contents)
    if not match:
        logging.warning('No version found in %s', pyproject_path)
        return 'unknown'

    return match.group('version')
