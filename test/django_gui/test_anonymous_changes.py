#!/usr/bin/env python3
"""
Unit tests that the Django console's control views refuse changes from users
who aren't logged in, while still letting them view the console.

The templates disable these controls for anonymous users, but a form can be
submitted without them, so the views have to check too. These tests use
Django's test client with CSRF checks on, taking the CSRF token from the page
the way a browser would.

Run with: python -m pytest test/django_gui/test_anonymous_changes.py
"""
import logging
import os
import re
from unittest import mock

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_gui.settings')
django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.test import Client, TestCase, override_settings  # noqa: E402


@override_settings(ALLOWED_HOSTS=['testserver'])
class TestAnonymousChanges(TestCase):

    def setUp(self):
        # Refusals are logged as warnings; keep the test output clean
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

        self.api = mock.MagicMock()
        self.api.get_configuration.return_value = {
            'id': 'test_cruise', 'config_filename': '/nonexistent/cruise.yaml'}
        self.api.get_loggers.return_value = {}
        self.api.get_modes.return_value = ['off', 'on']
        self.api.get_active_mode.return_value = 'off'
        self.api.get_logger_config_names.return_value = ['gyr1->off', 'gyr1->net']
        self.api.get_logger_config_name.return_value = 'gyr1->off'
        self.api.get_logger_config.return_value = {'readers': []}
        patcher = mock.patch('django_gui.views.api', self.api)
        patcher.start()
        self.addCleanup(patcher.stop)

        load_patcher = mock.patch('django_gui.views.load_cruise_definition',
                                  return_value=[])
        self.load_cruise_definition = load_patcher.start()
        self.addCleanup(load_patcher.stop)

        self.client = Client(enforce_csrf_checks=True)

    def post(self, url, data, token_url=None):
        """POST to url with a CSRF token taken from the page at token_url
        (default: url). The token is valid site-wide, so a page with no form
        of its own can be posted to with a token from another page."""
        token_url = token_url or url
        page = self.client.get(token_url)
        self.assertEqual(page.status_code, 200)
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',
                          page.content.decode())
        self.assertIsNotNone(token, 'no CSRF token on ' + token_url)
        return self.client.post(url, dict(data, csrfmiddlewaretoken=token.group(1)))

    def login(self):
        user = User.objects.create_user('tech', password='secret')
        self.client.force_login(user)

    ############################
    def test_anonymous_can_view(self):
        for url in ['/', '/change_mode/', '/edit_config/gyr1', '/choose_file/']:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_anonymous_mode_change_refused(self):
        response = self.post('/change_mode/', {'select_mode': 'on'})
        self.assertEqual(response.status_code, 403)
        self.api.set_active_mode.assert_not_called()

    def test_anonymous_logger_config_change_refused(self):
        response = self.post('/edit_config/gyr1',
                             {'update': 'Update', 'select_config': 'gyr1->net'})
        self.assertEqual(response.status_code, 403)
        self.api.set_active_logger_config.assert_not_called()

    def test_anonymous_delete_refused(self):
        response = self.post('/', {'delete_cruise': 'Delete'}, token_url='/change_mode/')
        self.assertEqual(response.status_code, 403)
        self.api.delete_configuration.assert_not_called()

    def test_anonymous_reload_refused(self):
        response = self.post('/', {'reload_button': ''}, token_url='/change_mode/')
        self.assertEqual(response.status_code, 403)
        self.load_cruise_definition.assert_not_called()

    def test_anonymous_load_refused(self):
        response = self.post('/choose_file/', {'target_file': '/tmp/cruise.yaml'})
        self.assertEqual(response.status_code, 403)
        self.load_cruise_definition.assert_not_called()

    def test_anonymous_can_close_window(self):
        response = self.post('/edit_config/gyr1', {'close': 'Close'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'window.close()', response.content)

    ############################
    def test_logged_in_mode_change_allowed(self):
        self.login()
        response = self.post('/change_mode/', {'select_mode': 'on'})
        self.assertEqual(response.status_code, 200)
        self.api.set_active_mode.assert_called_once_with('on')

    def test_logged_in_logger_config_change_allowed(self):
        self.login()
        self.post('/edit_config/gyr1',
                  {'update': 'Update', 'select_config': 'gyr1->net'})
        self.api.set_active_logger_config.assert_called_once_with('gyr1', 'gyr1->net')

    def test_logged_in_load_allowed(self):
        self.login()
        self.post('/choose_file/', {'target_file': '/tmp/cruise.yaml'})
        self.load_cruise_definition.assert_called_once_with('/tmp/cruise.yaml')
