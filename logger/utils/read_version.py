#!/usr/bin/env python3
"""Utility for reading the OpenRVDAS release version.

The version is derived from git tags (see the [tool.setuptools_scm] section
of pyproject.toml) rather than hand-maintained as a static string, so it
can't drift from what's actually tagged/released.

For an editable install (`pip install -e .`, as utils/install_openrvdas.sh
does), pip only computes this once, at install time, and freezes it into
the package's dist-info metadata - a plain `git pull` on an already-installed
checkout won't update it. So get_version() first asks setuptools_scm to
recompute the version live from the current git tree, and only falls back
to the installed package's (possibly stale) metadata if that's not
possible - e.g. no .git directory present (a non-editable install from a
built wheel/sdist), or setuptools_scm isn't available in this environment.
"""
import importlib.metadata
import logging
from pathlib import Path

# Root of the git checkout: three levels up from this file
# (logger/utils/read_version.py -> logger/utils -> logger -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[2]


###############################################################################
def get_version() -> str:
    """
    Return the OpenRVDAS version.

    Returns:
        The version string (e.g. "2.6.1", or "2.6.2.dev3+g1234567" for an
        untagged commit). Prefers a live read of the current git tree;
        falls back to the installed package's metadata, then to "unknown"
        if neither is available.
    """
    try:
        import setuptools_scm
        return setuptools_scm.get_version(root=str(_REPO_ROOT))
    except Exception:
        # No .git tree to read (non-editable install), setuptools_scm isn't
        # installed in this environment, or some other lookup failure -
        # fall back to whatever version was frozen in at install time.
        pass

    try:
        return importlib.metadata.version('openrvdas')
    except importlib.metadata.PackageNotFoundError:
        logging.warning('OpenRVDAS is not installed as a package; can\'t determine its version.')
        return 'unknown'
