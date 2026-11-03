#!/usr/bin/env python3
"""
Unit tests for the window-opening code in django_gui/static/django_gui/
index.html.js (issue #653): clicking a logger or mode button should open
a window, or bring the window to the front if one is already open.

The JavaScript is run under Node.js, with a stand-in for the browser's
"window", so these tests are skipped if node is not installed.

Run with: python -m pytest test/django_gui/test_index_js.py
"""
import json
import os
import shutil
import subprocess
import unittest

JS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'django_gui', 'static', 'django_gui', 'index.html.js')

# Loads index.html.js with a fake browser, runs the statements in SCENARIO,
# and prints the resulting value of "result" as JSON.
HARNESS = r"""
const fs = require('fs'), vm = require('vm');

// A stand-in for the browser's handling of named windows: opening a name
// that is already open returns the existing window, and only navigates it
// if a URL was given.
const windows = {};
let windows_created = 0;
let block_popups = false;

const browser_window = {
  location: {href: 'https://console.example/'},
  open: function(url, name, features) {
    if (block_popups) return null;
    let child = windows[name];
    if (!child || child.closed) {
      child = {name: name, closed: false, times_focused: 0,
               location: {href: 'about:blank'},
               focus: function() { this.times_focused++; }};
      windows[name] = child;
      windows_created++;
    }
    if (url) child.location.href = new URL(url, this.location.href).href;
    return child;
  }
};

const sandbox = {
  window: browser_window, URL: URL, Date: Date,
  console: {log: function() {}},
  document: {getElementById: function() { return null; }},
  setInterval: function() { return 0; }, setTimeout: function() { return 0; },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.env.INDEX_JS_FILE, 'utf8'), sandbox);

const click = {clientX: 10, clientY: 20};
const edit = (logger) => sandbox.open_edit_config(click, logger);
const mode = () => sandbox.open_change_mode(click);
const choose = () => sandbox.open_load_definition(click);
const summary = () => Object.keys(windows).sort().map((name) => ({
  name: name, href: windows[name].location.href,
  times_focused: windows[name].times_focused, closed: windows[name].closed}));

let result;
SCENARIO
console.log(JSON.stringify(result));
"""


@unittest.skipUnless(shutil.which('node'), 'Node.js is not installed')
class TestOpenOrFocusWindow(unittest.TestCase):

    def run_scenario(self, scenario):
        script = HARNESS.replace('SCENARIO', scenario)
        completed = subprocess.run(['node', '-e', script],
                                   env=dict(os.environ, INDEX_JS_FILE=JS_FILE),
                                   capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    ############################
    def test_first_click_opens_window(self):
        result = self.run_scenario("""
            edit('gyro');
            result = {created: windows_created, windows: summary()};
        """)
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['windows'], [
            {'name': 'openrvdas_edit_config_gyro',
             'href': 'https://console.example/edit_config/gyro',
             'times_focused': 1, 'closed': False}])

    ############################
    def test_second_click_focuses_existing_window(self):
        result = self.run_scenario("""
            edit('gyro');
            edit('gyro');
            edit('gyro');
            result = {created: windows_created, windows: summary()};
        """)
        self.assertEqual(result['created'], 1)
        self.assertEqual(len(result['windows']), 1)
        self.assertEqual(result['windows'][0]['times_focused'], 3)

    ############################
    def test_existing_window_is_not_reloaded(self):
        """Reloading would lose a selection the user hadn't yet submitted."""
        result = self.run_scenario("""
            edit('gyro');
            windows['openrvdas_edit_config_gyro'].location.href =
                'https://console.example/edit_config/gyro#touched';
            edit('gyro');
            result = summary();
        """)
        self.assertEqual(result[0]['href'],
                         'https://console.example/edit_config/gyro#touched')

    ############################
    def test_each_logger_gets_its_own_window(self):
        result = self.run_scenario("""
            edit('gyro');
            edit('knud');
            edit('gyro');
            result = {created: windows_created, windows: summary()};
        """)
        self.assertEqual(result['created'], 2)
        self.assertEqual(
            [(w['name'], w['href'], w['times_focused']) for w in result['windows']],
            [('openrvdas_edit_config_gyro',
              'https://console.example/edit_config/gyro', 2),
             ('openrvdas_edit_config_knud',
              'https://console.example/edit_config/knud', 1)])

    ############################
    def test_mode_window(self):
        result = self.run_scenario("""
            mode();
            mode();
            edit('gyro');
            result = {created: windows_created, windows: summary()};
        """)
        self.assertEqual(result['created'], 2)   # one for mode, one for gyro
        mode_window = [w for w in result['windows']
                       if w['name'] == 'openrvdas_change_mode'][0]
        self.assertEqual(mode_window['href'], 'https://console.example/change_mode/')
        self.assertEqual(mode_window['times_focused'], 2)

    ############################
    def test_load_definition_window(self):
        result = self.run_scenario("""
            choose();
            choose();
            result = {created: windows_created, windows: summary()};
        """)
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['windows'][0]['href'],
                         'https://console.example/choose_file/')
        self.assertEqual(result['windows'][0]['times_focused'], 2)

    ############################
    def test_closed_window_is_reopened(self):
        result = self.run_scenario("""
            edit('gyro');
            windows['openrvdas_edit_config_gyro'].closed = true;
            edit('gyro');
            result = {created: windows_created, windows: summary()};
        """)
        self.assertEqual(result['created'], 2)
        self.assertEqual(result['windows'], [
            {'name': 'openrvdas_edit_config_gyro',
             'href': 'https://console.example/edit_config/gyro',
             'times_focused': 1, 'closed': False}])

    ############################
    def test_blocked_popup_does_not_raise(self):
        result = self.run_scenario("""
            block_popups = true;
            result = {returned: edit('gyro') === undefined ? 'undefined' : 'other',
                      helper: sandbox.open_or_focus_window('../x/', 'x', []),
                      created: windows_created};
        """)
        self.assertEqual(result, {'returned': 'undefined', 'helper': None,
                                  'created': 0})


if __name__ == '__main__':
    unittest.main()
