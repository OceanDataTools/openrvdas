#!/usr/bin/env python3
"""Unit tests for read_version utility module.
"""
import logging
import os
import tempfile
import unittest

LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
logging.basicConfig(format=LOGGING_FORMAT)

from logger.utils.read_version import get_version  # noqa: E402


class TestReadVersion(unittest.TestCase):
    """Test cases for get_version()."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_pyproject(self, content):
        full_path = os.path.join(self.base_dir, 'pyproject.toml')
        with open(full_path, 'w') as f:
            f.write(content)
        return full_path

    def test_reads_project_version(self):
        pyproject_path = self.create_pyproject(
            '[project]\n'
            'name = "openrvdas"\n'
            'version = "1.2.3"\n'
        )
        self.assertEqual(get_version(pyproject_path), '1.2.3')

    def test_ignores_inline_dependency_version_constraints(self):
        pyproject_path = self.create_pyproject(
            '[project]\n'
            'name = "openrvdas"\n'
            'version = "1.2.3"\n'
            'dependencies = ["PyYAML"]\n'
            '\n'
            '[tool.poetry.dependencies]\n'
            'fastapi = {extras = ["all"], version = "^0.135.0"}\n'
        )
        self.assertEqual(get_version(pyproject_path), '1.2.3')

    def test_missing_file_returns_unknown(self):
        missing_path = os.path.join(self.base_dir, 'does_not_exist.toml')
        self.assertEqual(get_version(missing_path), 'unknown')

    def test_missing_version_returns_unknown(self):
        pyproject_path = self.create_pyproject('[project]\nname = "openrvdas"\n')
        self.assertEqual(get_version(pyproject_path), 'unknown')

    def test_default_path_reads_real_pyproject(self):
        # Sanity check that the default path resolves to the repo's actual
        # pyproject.toml and returns a non-trivial version string.
        version = get_version()
        self.assertNotEqual(version, 'unknown')


if __name__ == '__main__':
    unittest.main()
