#!/usr/bin/env python3
"""Utility for reading the installed OpenRVDAS release version.

The version is derived from git tags via setuptools_scm at install time
(see the [tool.setuptools_scm] section of pyproject.toml) rather than
hand-maintained as a static string, so it can't drift from what's actually
tagged/released. This reads it back out of the installed package's
metadata, which is populated whenever OpenRVDAS is installed (e.g. via
`pip install -e .`, as utils/install_openrvdas.sh does).
"""
import importlib.metadata
import logging


###############################################################################
def get_version() -> str:
    """
    Return the installed OpenRVDAS version.

    Returns:
        The version string (e.g. "2.6.1", or "2.6.2.dev3+g1234567" for an
        untagged commit), or "unknown" if OpenRVDAS isn't installed as a
        package in the current environment.
    """
    try:
        return importlib.metadata.version('openrvdas')
    except importlib.metadata.PackageNotFoundError:
        logging.warning('OpenRVDAS is not installed as a package; can\'t determine its version.')
        return 'unknown'
