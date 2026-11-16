#!/usr/bin/env python3
"""
Unit tests for how django_gui/static/django_gui/index.html.js handles
status messages from the CachedDataServer (issue #755):

  - The "Definition is stale" notice is hidden again once a newer cruise
    definition arrives.
  - After the websocket reconnects, the page resubscribes to each logger's
    stderr, even though the list of loggers hasn't changed.

The JavaScript is run under Node.js, with a stand-in for the browser's
document, so these tests are skipped if node is not installed.

Run with: python -m pytest test/django_gui/test_index_js_status.py
"""
import json
import os
import shutil
import subprocess
import unittest

JS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'django_gui', 'static', 'django_gui')

# Loads index.html.js (and the stderr_log_utils.js it relies on) with a fake
# document, runs the statements in SCENARIO, and prints the resulting value
# of "result" as JSON.
HARNESS = r"""
const fs = require('fs'), vm = require('vm');

// A stand-in for the few DOM features the page uses. Any id can be looked
// up; elements are created on first use.
function make_element() {
  return {
    style: {}, innerHTML: '', children: [], rows: [],
    classList: {add: function() {}, remove: function() {}},
    setAttribute: function() {},
    appendChild: function(child) { this.children.push(child); this.rows.push(child); },
    deleteRow: function(i) { this.rows.splice(i, 1); },
  };
}
const elements = {};
const document = {
  getElementById: function(id) {
    if (!elements[id]) elements[id] = make_element();
    return elements[id];
  },
  createElement: function() { return make_element(); },
};

// What the page sends to the server (send() is defined in websocket.js).
const sent = [];

const sandbox = {
  window: {}, URL: URL, Date: Date, document: document,
  console: {log: function() {}},
  setInterval: function() { return 0; }, clearInterval: function() {},
  setTimeout: function() { return 0; }, clearTimeout: function() {},
  send: function(message) { sent.push(message); },
};
vm.createContext(sandbox);
for (const name of ['stderr_log_utils.js', 'index.html.js']) {
  vm.runInContext(fs.readFileSync(process.env.JS_DIR + '/' + name, 'utf8'), sandbox);
}

// Deliver one data message from the server, as websocket.js would.
const deliver = (fields) => sandbox.process_message(
  JSON.stringify({type: 'data', status: 200, data: fields}));
const definition = (timestamp) => ({'status:cruise_definition': [[timestamp, {
  cruise_id: 'test', filename: 'test.yaml', active_mode: 'off',
  modes: {off: {}}, loggers: {gyr1: {active: 'gyr1->off'},
                              knud: {active: 'knud->off'}}}]]});
const reload_display = () => document.getElementById('reload_span').style.display;
const subscribed_stderr = () => sent.filter((m) => m.type == 'subscribe')
  .map((m) => Object.keys(m.fields).filter((f) => f.startsWith('stderr:logger:')))
  .filter((fields) => fields.length).map((fields) => fields.sort());

let result;
SCENARIO
console.log(JSON.stringify(result));
"""


@unittest.skipUnless(shutil.which('node'), 'Node.js is not installed')
class TestIndexStatusMessages(unittest.TestCase):

    def run_scenario(self, scenario):
        script = HARNESS.replace('SCENARIO', scenario)
        completed = subprocess.run(['node', '-e', script],
                                   env=dict(os.environ, JS_DIR=JS_DIR),
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_new_definition_clears_stale_notice(self):
        result = self.run_scenario("""
          deliver(definition(100));
          deliver({'status:file_update': [[150, 140]]});
          const shown = reload_display();
          deliver(definition(200));   // e.g. from "Load new definition"
          result = {shown: shown, after_load: reload_display()};
        """)
        self.assertEqual(result, {'shown': 'inline', 'after_load': 'none'})

    def test_stale_notice_returns_if_file_changes_again(self):
        result = self.run_scenario("""
          deliver(definition(100));
          deliver({'status:file_update': [[150, 140]]});
          deliver(definition(200));
          deliver({'status:file_update': [[250, 240]]});
          result = reload_display();
        """)
        self.assertEqual(result, 'inline')

    def test_reconnect_resubscribes_to_logger_stderr(self):
        # After a reconnect, the server resends the same definition, with
        # the same timestamp, from its cache.
        result = self.run_scenario("""
          sandbox.initial_send_message();   // first connection
          deliver(definition(100));
          sandbox.initial_send_message();   // reconnection
          deliver(definition(100));
          result = subscribed_stderr();
        """)
        self.assertEqual(result, [['stderr:logger:gyr1', 'stderr:logger:knud'],
                                  ['stderr:logger:gyr1', 'stderr:logger:knud']])

    def test_reconnect_clears_logger_manager_stderr(self):
        # The server resends the last hour of logger manager messages on
        # reconnect, so the old ones are cleared rather than shown twice.
        result = self.run_scenario("""
          sandbox.initial_send_message();
          deliver({'stderr:logger_manager': [[100, 'started']]});
          const before = document.getElementById('logger_manager_stderr').innerHTML;
          sandbox.initial_send_message();
          result = {before: before.length > 0,
                    after: document.getElementById('logger_manager_stderr').innerHTML};
        """)
        self.assertEqual(result, {'before': True, 'after': ''})

    def test_unchanged_definition_without_reconnect_does_not_resubscribe(self):
        # Without a reconnect, a repeated definition shouldn't rebuild the
        # table or resubscribe.
        result = self.run_scenario("""
          sandbox.initial_send_message();
          deliver(definition(100));
          deliver(definition(200));
          result = subscribed_stderr().length;
        """)
        self.assertEqual(result, 1)


if __name__ == '__main__':
    unittest.main()
