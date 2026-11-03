#!/usr/bin/env python3
"""
Unit tests for how django_gui/views.py reports errors when loading or
reloading a cruise definition (issue #652).

Run with: python -m pytest test/django_gui/test_load_errors.py
"""
import django
import html
import logging
import os
import tempfile
from unittest import mock

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_gui.settings')
django.setup()

from django.test import TestCase, override_settings  # noqa: E402

from django_gui import views  # noqa: E402

VALID_DEFINITION = """
cruise:
  id: test_cruise
loggers:
  gyro:
    configs: [gyro->off, gyro->on]
modes:
  "off":
    gyro: gyro->off
  "on":
    gyro: gyro->on
default_mode: "off"
configs:
  gyro->off: {}
  gyro->on:
    readers:
      class: TextFileReader
"""

# A mode refers to two configs that don't exist
BAD_REFERENCES = VALID_DEFINITION.replace(
    'gyro: gyro->off', 'gyro: gyro->missing').replace(
    'gyro: gyro->on\n', 'gyro: gyro->also_missing\n')

BAD_SYNTAX = """
cruise:
  id: test_cruise
loggers:
  gyro: [unclosed
"""


@override_settings(ALLOWED_HOSTS=['testserver'])
class TestLoadErrors(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.filename = os.path.join(self.tmpdir.name, 'cruise.yaml')

        # Errors are logged as well as displayed; keep the test output clean
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

        self.api = mock.MagicMock()
        self.api.get_configuration.return_value = {
            'id': 'test_cruise', 'config_filename': self.filename}
        self.api.get_loggers.return_value = {}
        self.api.get_modes.return_value = ['off', 'on']
        self.api.get_active_mode.return_value = 'on'
        self.api.get_default_mode.return_value = 'off'
        patcher = mock.patch('django_gui.views.api', self.api)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write(self, content):
        with open(self.filename, 'w') as f:
            f.write(content)

    def _reload(self):
        resp = self.client.post('/', {'reload_button': ''})
        self.assertEqual(resp.status_code, 200)
        return html.unescape(resp.content.decode())

    def _load(self):
        return self.client.post('/choose_file/', {'target_file': self.filename})

    ############################
    # Reloading a stale definition
    def test_reload_ok(self):
        self._write(VALID_DEFINITION)
        page = self._reload()

        self.assertNotIn('id="load_errors"', page)
        self.api.load_configuration.assert_called_once()
        config = self.api.load_configuration.call_args[0][0]
        self.assertTrue(config['preserve_mode'])
        self.assertEqual(config['cruise']['config_filename'], self.filename)
        # A reload shouldn't revert to the default mode
        self.api.set_active_mode.assert_not_called()

    def test_reload_error_is_displayed(self):
        self._write(BAD_REFERENCES)
        page = self._reload()

        self.assertIn('id="load_errors"', page)
        self.assertIn('Could not reload "%s"' % self.filename, page)
        self.assertIn('already loaded is still in effect', page)
        # We should be told about all of the problems, not just the first
        self.assertIn("'gyro->missing'", page)
        self.assertIn("'gyro->also_missing'", page)
        self.api.load_configuration.assert_not_called()

    def test_reload_syntax_error_says_what_and_where(self):
        self._write(BAD_SYNTAX)
        page = self._reload()

        self.assertIn('id="load_errors"', page)
        self.assertIn('Invalid YAML syntax in "%s"' % self.filename, page)
        self.assertIn('line 5', page)
        # ...rather than complaining about the resulting empty definition
        self.assertNotIn("must have a 'loggers' key", page)
        self.api.load_configuration.assert_not_called()

    def test_reload_missing_file(self):
        page = self._reload()   # we never created the file

        self.assertIn('id="load_errors"', page)
        self.assertIn('YAML file not found: "%s"' % self.filename, page)
        self.assertNotIn("must have a 'loggers' key", page)
        self.api.load_configuration.assert_not_called()

    def test_reload_with_nothing_loaded(self):
        self.api.get_configuration.side_effect = ValueError('no cruise')
        page = self._reload()

        self.assertIn('id="load_errors"', page)
        self.assertIn('There is no cruise definition file to reload', page)
        self.api.load_configuration.assert_not_called()

    def test_reload_error_from_load_configuration(self):
        """An error raised when the definition is installed is shown too."""
        self._write(VALID_DEFINITION)
        self.api.load_configuration.side_effect = ValueError('Cruise is cursed')
        page = self._reload()

        self.assertIn('id="load_errors"', page)
        self.assertIn('Cruise is cursed', page)

    def test_unexpected_error_is_displayed(self):
        self._write(VALID_DEFINITION)
        self.api.load_configuration.side_effect = KeyError('surprise')
        page = self._reload()

        self.assertIn('id="load_errors"', page)
        self.assertIn('Unexpected error (KeyError)', page)
        self.assertIn('surprise', page)

    def test_no_error_box_on_plain_page_load(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('id="load_errors"', resp.content.decode())

    ############################
    # Loading a new definition from the file chooser
    def test_load_ok(self):
        self._write(VALID_DEFINITION)
        resp = self._load()

        self.assertEqual(resp.content.decode(), '<script>window.close()</script>')
        self.api.load_configuration.assert_called_once()
        config = self.api.load_configuration.call_args[0][0]
        self.assertNotIn('preserve_mode', config)
        # A new definition starts in its default mode
        self.api.set_active_mode.assert_called_once_with('off')

    def test_load_error_is_displayed(self):
        self._write(BAD_REFERENCES)
        resp = self._load()
        self.assertEqual(resp.status_code, 200)
        page = html.unescape(resp.content.decode())

        self.assertIn('id="load_errors"', page)
        self.assertIn('Could not load "%s"' % self.filename, page)
        self.assertIn("'gyro->missing'", page)
        self.assertIn("'gyro->also_missing'", page)
        self.api.load_configuration.assert_not_called()
        self.api.set_active_mode.assert_not_called()

    def test_load_syntax_error_says_what_and_where(self):
        self._write(BAD_SYNTAX)
        page = html.unescape(self._load().content.decode())

        self.assertIn('id="load_errors"', page)
        self.assertIn('Invalid YAML syntax in "%s"' % self.filename, page)
        self.assertNotIn("must have a 'loggers' key", page)

    ############################
    def test_error_text_is_escaped(self):
        """Error text comes from the file's contents, so mustn't be markup."""
        self._write(VALID_DEFINITION)
        self.api.load_configuration.side_effect = ValueError(
            'bad <script>alert(1)</script> value')
        raw_page = self.client.post('/', {'reload_button': ''}).content.decode()

        self.assertNotIn('<script>alert(1)</script>', raw_page)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', raw_page)

    ############################
    def test_helper_returns_errors(self):
        self._write(BAD_REFERENCES)
        errors = views.load_cruise_definition(self.filename)
        self.assertEqual(len(errors), 2)

        self._write(VALID_DEFINITION)
        self.assertEqual(views.load_cruise_definition(self.filename), [])


if __name__ == '__main__':
    import unittest
    unittest.main()
