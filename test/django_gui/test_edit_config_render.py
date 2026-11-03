#!/usr/bin/env python3
"""
Unit tests for the logger config display in django_gui/views.py edit_config.

Run with: ./manage.py test test.django_gui.test_edit_config_render
Or: python -m pytest test/django_gui/test_edit_config_render.py
"""
import django
import os
import json
import yaml
import unittest
from unittest import mock

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_gui.settings')
django.setup()

from django.test import TestCase, override_settings  # noqa: E402

CONFIG = {
    'name': 'gyr1->net',
    'readers': [{'class': 'SerialReader',
                 'kwargs': {'port': '/dev/ttyr15', 'baudrate': 9600}}],
    'transforms': [{'class': 'TimestampTransform'},
                   {'class': 'PrefixTransform', 'kwargs': {'prefix': 'gyr1'}}],
    'writers': [{'class': 'UDPWriter', 'kwargs': {'port': 6224}}],
}


@override_settings(ALLOWED_HOSTS=['testserver'])
class TestEditConfigRendersYAML(TestCase):
    def _get(self):
        api = mock.MagicMock()
        api.get_active_mode.return_value = 'underway'
        api.get_logger_config_names.return_value = ['off', 'gyr1->net']
        api.get_logger_config_name.side_effect = lambda *a, **k: 'gyr1->net'
        api.get_logger_config.side_effect = lambda name: (
            CONFIG if name == 'gyr1->net' else {'name': 'off'})
        with mock.patch('django_gui.views.api', api):
            return self.client.get('/edit_config/gyr1')

    def test_yaml_is_rendered(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()

        # The config map is emitted by json_script as a JSON object whose
        # values are YAML strings.
        start = html.index('id="config_map"')
        start = html.index('>', start) + 1
        payload = html[start:html.index('</script>', start)]
        config_map = json.loads(payload)

        yaml_text = config_map['gyr1->net']
        self.assertIn('class: SerialReader', yaml_text)
        self.assertNotIn('{', yaml_text.split('\n')[0])   # block style, not flow

        # It must be valid YAML that round-trips to the original config
        self.assertEqual(yaml.safe_load(yaml_text), CONFIG)

        # ... and key order must be preserved, not alphabetized
        top_keys = [ln.split(':')[0] for ln in yaml_text.split('\n')
                    if ln and not ln.startswith((' ', '-'))]
        self.assertEqual(top_keys, ['name', 'readers', 'transforms', 'writers'])

    def test_no_json_viewer_left(self):
        html = self._get().content.decode()
        self.assertNotIn('JSONViewer', html)
        self.assertNotIn('json-viewer', html)
        self.assertIn('id="config_yaml"', html)

    def test_html_in_config_is_not_injected_as_markup(self):
        """A config value containing markup must not become live HTML."""
        api = mock.MagicMock()
        api.get_active_mode.return_value = 'underway'
        api.get_logger_config_names.return_value = ['evil']
        api.get_logger_config_name.side_effect = lambda *a, **k: 'evil'
        api.get_logger_config.return_value = {
            'name': '</script><img src=x onerror=alert(1)>'}
        with mock.patch('django_gui.views.api', api):
            html = self.client.get('/edit_config/gyr1').content.decode()
        self.assertNotIn('<img src=x', html)


if __name__ == '__main__':
    unittest.main()
