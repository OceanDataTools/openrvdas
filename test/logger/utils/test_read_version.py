#!/usr/bin/env python3
"""Unit tests for read_version utility module.
"""
import importlib.metadata
import logging
import unittest
from unittest.mock import patch

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
logging.basicConfig(format=LOGGING_FORMAT)

from logger.utils.read_version import get_version  # noqa: E402


class TestReadVersion(unittest.TestCase):
    """Test cases for get_version()."""

    def test_prefers_live_scm_version(self):
        with patch('setuptools_scm.get_version', return_value='2.6.2.dev3+g1234567') as mock_scm, \
                patch('importlib.metadata.version') as mock_metadata:
            self.assertEqual(get_version(), '2.6.2.dev3+g1234567')
            mock_scm.assert_called_once()
            mock_metadata.assert_not_called()

    def test_falls_back_to_installed_metadata_when_scm_lookup_fails(self):
        with patch('setuptools_scm.get_version', side_effect=LookupError), \
                patch('importlib.metadata.version', return_value='2.6.1') as mock_version:
            self.assertEqual(get_version(), '2.6.1')
            mock_version.assert_called_once_with('openrvdas')

    def test_falls_back_to_installed_metadata_when_scm_not_installed(self):
        with patch.dict('sys.modules', {'setuptools_scm': None}), \
                patch('importlib.metadata.version', return_value='2.6.1') as mock_version:
            self.assertEqual(get_version(), '2.6.1')
            mock_version.assert_called_once_with('openrvdas')

    def test_returns_unknown_when_neither_available(self):
        with patch('setuptools_scm.get_version', side_effect=LookupError), \
                patch(
                    'importlib.metadata.version',
                    side_effect=importlib.metadata.PackageNotFoundError,
                ):
            self.assertEqual(get_version(), 'unknown')

    def test_matches_real_environment(self):
        # Sanity check against the real environment: get_version() should
        # return something non-empty whenever either a live git checkout or
        # an installed package is available.
        try:
            importlib.metadata.version('openrvdas')
        except importlib.metadata.PackageNotFoundError:
            self.skipTest('openrvdas is not installed in this environment')
        self.assertTrue(get_version())


if __name__ == '__main__':
    unittest.main()
