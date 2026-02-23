#!/usr/bin/env python3
"""
Unit tests for django_gui/api_views.py REST API endpoints.

Run with: ./manage.py test test.django_gui.test_api_views
Or: python -m pytest test/django_gui/test_api_views.py
"""

import django
import os
import sys
import unittest
from unittest import mock

sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_gui.settings')
django.setup()

from django.test import TestCase, override_settings  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from rest_framework.authtoken.models import Token  # noqa: E402


# Sample cruise configuration for testing
SAMPLE_CRUISE_CONFIG = {
    "cruise": {
        "id": "test_cruise",
        "start": "2024-01-01",
        "end": "2024-02-01"
    },
    "loggers": {
        "test_logger": {
            "configs": ["off", "test->net"]
        }
    },
    "modes": {
        "off": {"test_logger": "off"},
        "running": {"test_logger": "test->net"}
    },
    "default_mode": "off",
    "configs": {
        "off": {},
        "test->net": {"test_logger": "config test->net"}
    }
}


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class TestApiViewsBase(TestCase):
    """Base class with common setup for API view tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create a test user
        cls.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        cls.token = Token.objects.create(user=cls.user)

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')


class TestLoadConfigurationFileAPIView(TestApiViewsBase):
    """Tests for the load-configuration-file endpoint."""

    @mock.patch('django_gui.api_views._get_api')
    @mock.patch('django_gui.api_views.read_config')
    @mock.patch('django_gui.api_views.expand_cruise_definition')
    def test_load_configuration_file_success(self, mock_expand, mock_read, mock_get_api):
        """Test successful loading of a configuration file."""
        # Setup mocks
        mock_read.return_value = SAMPLE_CRUISE_CONFIG.copy()
        mock_expand.return_value = SAMPLE_CRUISE_CONFIG.copy()

        mock_api = mock.MagicMock()
        mock_api.get_default_mode.return_value = 'off'
        mock_get_api.return_value = mock_api

        # Create a temp file path (doesn't need to exist since we mock read_config)
        target_file = '/tmp/test_cruise.yaml'

        response = self.client.post(
            '/api/load-configuration-file/',
            {'target_file': target_file},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('loaded', response.data['status'])

        # Verify the mocks were called correctly
        mock_read.assert_called_once_with(target_file)
        mock_expand.assert_called_once()
        mock_api.load_configuration.assert_called_once()
        mock_api.set_active_mode.assert_called_once_with('off')

    @mock.patch('django_gui.api_views._get_api')
    @mock.patch('django_gui.api_views.read_config')
    @mock.patch('django_gui.api_views.expand_cruise_definition')
    def test_load_configuration_file_with_cruise_section(
            self, mock_expand, mock_read, mock_get_api):
        """Test that config_filename is added to cruise section."""
        config_with_cruise = SAMPLE_CRUISE_CONFIG.copy()
        mock_read.return_value = config_with_cruise
        mock_expand.return_value = config_with_cruise

        mock_api = mock.MagicMock()
        mock_api.get_default_mode.return_value = 'off'
        mock_get_api.return_value = mock_api

        target_file = '/path/to/cruise.yaml'

        response = self.client.post(
            '/api/load-configuration-file/',
            {'target_file': target_file},
            format='json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify load_configuration was called with config that has config_filename set
        call_args = mock_api.load_configuration.call_args[0][0]
        self.assertEqual(call_args['cruise']['config_filename'], target_file)

    @mock.patch('django_gui.api_views._get_api')
    @mock.patch('django_gui.api_views.read_config')
    def test_load_configuration_file_invalid_yaml(self, mock_read, mock_get_api):
        """Test handling of invalid YAML file."""
        import yaml
        mock_read.side_effect = yaml.scanner.ScannerError("Invalid YAML")

        mock_api = mock.MagicMock()
        mock_get_api.return_value = mock_api

        response = self.client.post(
            '/api/load-configuration-file/',
            {'target_file': '/tmp/invalid.yaml'},
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('errors', response.data)

    def test_load_configuration_file_missing_target(self):
        """Test that missing target_file returns error."""
        response = self.client.post(
            '/api/load-configuration-file/',
            {},
            format='json'
        )

        self.assertEqual(response.status_code, 400)

    def test_load_configuration_file_unauthenticated(self):
        """Test that unauthenticated requests are rejected."""
        client = APIClient()  # No credentials
        response = client.post(
            '/api/load-configuration-file/',
            {'target_file': '/tmp/test.yaml'},
            format='json'
        )

        self.assertEqual(response.status_code, 401)


class TestCruiseReloadCurrentConfigurationAPIView(TestApiViewsBase):
    """Tests for the reload-current-configuration endpoint."""

    @mock.patch('django_gui.api_views._get_api')
    @mock.patch('django_gui.api_views.read_config')
    @mock.patch('django_gui.api_views.expand_cruise_definition')
    def test_reload_configuration_success(self, mock_expand, mock_read, mock_get_api):
        """Test successful reload of current configuration."""
        # Setup mocks
        current_config = {
            'id': 'test_cruise',
            'config_filename': '/path/to/current.yaml'
        }

        mock_api = mock.MagicMock()
        mock_api.get_configuration.return_value = current_config
        mock_get_api.return_value = mock_api

        reloaded_config = SAMPLE_CRUISE_CONFIG.copy()
        mock_read.return_value = reloaded_config
        mock_expand.return_value = reloaded_config

        response = self.client.post(
            '/api/reload-current-configuration/',
            {'reload': 'true'},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('reloaded', response.data['status'].lower())

        # Verify read_config was called with the filename from current config
        mock_read.assert_called_once_with('/path/to/current.yaml')
        mock_expand.assert_called_once()
        mock_api.load_configuration.assert_called_once()

    @mock.patch('django_gui.api_views._get_api')
    def test_reload_configuration_no_current_config(self, mock_get_api):
        """Test reload when no configuration is loaded."""
        mock_api = mock.MagicMock()
        mock_api.get_configuration.return_value = {}
        mock_get_api.return_value = mock_api

        response = self.client.post(
            '/api/reload-current-configuration/',
            {'reload': 'true'},
            format='json'
        )

        # Should return 400 since there's no config_filename
        self.assertEqual(response.status_code, 400)

    def test_reload_configuration_missing_reload_param(self):
        """Test that missing reload parameter returns error."""
        response = self.client.post(
            '/api/reload-current-configuration/',
            {},
            format='json'
        )

        self.assertEqual(response.status_code, 400)

    def test_reload_configuration_unauthenticated(self):
        """Test that unauthenticated requests are rejected."""
        client = APIClient()
        response = client.post(
            '/api/reload-current-configuration/',
            {'reload': 'true'},
            format='json'
        )

        self.assertEqual(response.status_code, 401)


class TestCruiseSelectModeAPIView(TestApiViewsBase):
    """Tests for the select-cruise-mode endpoint."""

    @mock.patch('django_gui.api_views._get_api')
    def test_select_mode_success(self, mock_get_api):
        """Test successful mode selection."""
        mock_api = mock.MagicMock()
        mock_get_api.return_value = mock_api

        response = self.client.post(
            '/api/select-cruise-mode/',
            {'select_mode': 'underway'},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        mock_api.set_active_mode.assert_called_once_with('underway')

    @mock.patch('django_gui.api_views._get_api')
    def test_select_mode_invalid(self, mock_get_api):
        """Test selecting an invalid mode."""
        mock_api = mock.MagicMock()
        mock_api.set_active_mode.side_effect = ValueError("Invalid mode")
        mock_get_api.return_value = mock_api

        response = self.client.post(
            '/api/select-cruise-mode/',
            {'select_mode': 'invalid_mode'},
            format='json'
        )

        self.assertEqual(response.status_code, 400)

    @mock.patch('django_gui.api_views._get_api')
    def test_get_modes(self, mock_get_api):
        """Test GET request returns available modes."""
        mock_api = mock.MagicMock()
        mock_api.get_modes.return_value = ['off', 'port', 'underway']
        mock_api.get_active_mode.return_value = 'port'
        mock_get_api.return_value = mock_api

        response = self.client.get('/api/select-cruise-mode/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['modes'], ['off', 'port', 'underway'])
        self.assertEqual(response.data['data']['active_mode'], 'port')


class TestCruiseDeleteConfigurationAPIView(TestApiViewsBase):
    """Tests for the delete-configuration endpoint."""

    @mock.patch('django_gui.api_views._get_api')
    def test_delete_configuration_success(self, mock_get_api):
        """Test successful configuration deletion."""
        mock_api = mock.MagicMock()
        mock_get_api.return_value = mock_api

        response = self.client.post(
            '/api/delete-configuration/',
            {'delete': 'true'},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        mock_api.delete_configuration.assert_called_once()

    @mock.patch('django_gui.api_views._get_api')
    def test_delete_configuration_error(self, mock_get_api):
        """Test handling of deletion error."""
        mock_api = mock.MagicMock()
        mock_api.delete_configuration.side_effect = ValueError("Cannot delete")
        mock_get_api.return_value = mock_api

        response = self.client.post(
            '/api/delete-configuration/',
            {'delete': 'true'},
            format='json'
        )

        self.assertEqual(response.status_code, 400)


class TestEditLoggerConfigAPIView(TestApiViewsBase):
    """Tests for the edit-logger-config endpoint."""

    @mock.patch('django_gui.api_views._get_api')
    def test_edit_logger_config_success(self, mock_get_api):
        """Test successful logger config update."""
        mock_api = mock.MagicMock()
        mock_get_api.return_value = mock_api

        response = self.client.post(
            '/api/edit-logger-config/',
            {
                'update': 'true',
                'logger_id': 'test_logger',
                'config': 'test->net'
            },
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        mock_api.set_active_logger_config.assert_called_once_with('test_logger', 'test->net')

    @mock.patch('django_gui.api_views._get_api')
    def test_get_loggers(self, mock_get_api):
        """Test GET request returns loggers list."""
        mock_api = mock.MagicMock()
        mock_api.get_loggers.return_value = {'logger1': {}, 'logger2': {}}
        mock_get_api.return_value = mock_api

        response = self.client.get('/api/edit-logger-config/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('loggers', response.data)


class TestCruiseConfigurationAPIView(TestApiViewsBase):
    """Tests for the cruise-configuration endpoint."""

    @mock.patch('django_gui.api_views._get_api')
    def test_get_cruise_configuration(self, mock_get_api):
        """Test GET request returns cruise configuration."""
        mock_api = mock.MagicMock()
        mock_api.get_configuration.return_value = {
            'id': 'test_cruise',
            'config_filename': '/path/to/config.yaml'
        }
        mock_api.get_loggers.return_value = {'logger1': {}}
        mock_api.get_modes.return_value = ['off', 'running']
        mock_api.get_active_mode.return_value = 'off'
        mock_get_api.return_value = mock_api

        response = self.client.get('/api/cruise-configuration/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'ok')
        self.assertIn('configuration', response.data)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    unittest.main(warnings='ignore', verbosity=args.verbosity + 1)
