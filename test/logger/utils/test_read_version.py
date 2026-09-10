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

    def test_returns_installed_package_version(self):
        with patch('importlib.metadata.version', return_value='2.6.1') as mock_version:
            self.assertEqual(get_version(), '2.6.1')
            mock_version.assert_called_once_with('openrvdas')

    def test_returns_unknown_when_not_installed(self):
        with patch(
            'importlib.metadata.version', side_effect=importlib.metadata.PackageNotFoundError
        ):
            self.assertEqual(get_version(), 'unknown')

    def test_matches_real_installed_version(self):
        # Sanity check against the real environment: if OpenRVDAS is
        # installed here (e.g. via `pip install -e .`), get_version() should
        # agree with importlib.metadata directly.
        try:
            expected = importlib.metadata.version('openrvdas')
        except importlib.metadata.PackageNotFoundError:
            self.skipTest('openrvdas is not installed in this environment')
        self.assertEqual(get_version(), expected)


if __name__ == '__main__':
    unittest.main()
