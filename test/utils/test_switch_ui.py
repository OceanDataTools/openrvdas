#!/usr/bin/env python3
"""
Tests for the CachedDataServer port check in utils/switch_ui.sh (issue #654).

Each test builds a fake installation - supervisor configs, nginx configs and
the React backend's .env - in a temporary directory, points the script at it
via SUPERVISOR_DIR and OPENRVDAS_ROOT, and checks what "status" reports.

The script is run with /bin/bash, which on MacOS is bash 3.2, so these tests
also check that the code runs under the oldest bash we support.

Run with: python -m pytest test/utils/test_switch_ui.py
"""
import os
import platform
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'utils', 'switch_ui.sh')

# The start of the warning we're testing for. (The script has other
# warnings, e.g. that supervisorctl isn't in the PATH we give it.)
PORT_WARNING = 'WARNING: the CachedDataServer listens on port'

NGINX_CONF = """
http {
    server {
        listen 80;
        location /cds-ws {
            proxy_pass http://localhost:%s;
            proxy_http_version 1.1;
        }
        location / {
            proxy_pass http://127.0.0.1:8000;
        }
    }
}
"""


@unittest.skipUnless(platform.system() in ('Darwin', 'Linux'),
                     'switch_ui.sh supports only MacOS and Linux')
class TestCDSPortCheck(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = os.path.join(self.tmpdir.name, 'openrvdas')
        self.supervisor_dir = os.path.join(self.tmpdir.name, 'supervisor.d')
        for path in (self.supervisor_dir,
                     os.path.join(self.root, 'django_gui'),
                     os.path.join(self.root, 'web_frontend'),
                     os.path.join(self.root, 'web_backend')):
            os.makedirs(path)

    def write(self, path, content):
        with open(path, 'w') as f:
            f.write(content)

    def supervisor_file(self, name):
        return os.path.join(self.supervisor_dir, 'openrvdas_%s.ini' % name)

    def install(self, cds_port=8766, logger_manager=':8766', django_nginx=8766,
                react_nginx=8766, react_env=8766):
        """Write a fake installation. Pass None to leave a file out."""
        if cds_port is not None:
            self.write(self.supervisor_file('cached_data'),
                       '; Supervisor configurations\n'
                       '[program:cached_data_server]\n'
                       'command=/venv/bin/python server/cached_data_server.py '
                       '--port %s --disk_cache /var/tmp/disk_cache -v\n'
                       'directory=%s\n' % (cds_port, self.root))
        self.write(self.supervisor_file('logger_manager'),
                   '; Supervisor configurations\n'
                   '[program:logger_manager]\n'
                   'command=/venv/bin/python server/logger_manager.py '
                   '--database django --data_server_websocket %s -v\n'
                   'directory=%s\n' % (logger_manager, self.root))
        # An enabled Django UI, so that there's a UI to switch away from
        self.write(self.supervisor_file('django'),
                   '; Supervisor configurations\n[program:nginx]\n')
        if django_nginx is not None:
            self.write(os.path.join(self.root, 'django_gui', 'openrvdas_nginx.conf'),
                       NGINX_CONF % django_nginx)
        if react_nginx is not None:
            self.write(os.path.join(self.root, 'web_frontend', 'openrvdas_nginx.conf'),
                       NGINX_CONF % react_nginx)
        if react_env is not None:
            self.write(os.path.join(self.root, 'web_backend', '.env'),
                       'SECRET_KEY=not-a-port-12345\n'
                       'CACHED_DATA_SERVER_HOST=localhost\n'
                       'CACHED_DATA_SERVER_PORT=%s\n' % react_env)

    def run_script(self, *args):
        env = dict(os.environ,
                   SUPERVISOR_DIR=self.supervisor_dir,
                   SUPERVISOR_SUFFIX='ini',
                   OPENRVDAS_ROOT=self.root,
                   # Keep supervisorctl out of reach, so we don't report on,
                   # or touch, any real installation on this machine.
                   PATH='/usr/bin:/bin')
        completed = subprocess.run(['/bin/bash', SCRIPT] + list(args),
                                   env=env, capture_output=True, text=True,
                                   timeout=60)
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + completed.stderr)
        return completed.stdout

    ############################
    def test_consistent_ports(self):
        self.install()
        output = self.run_script('status')
        self.assertNotIn(PORT_WARNING, output)
        self.assertNotIn('NOTE', output)

    def test_consistent_non_default_port(self):
        self.install(cds_port=55152, logger_manager=':55152', django_nginx=55152,
                     react_nginx=55152, react_env=55152)
        self.assertNotIn(PORT_WARNING, self.run_script('status'))

    def test_nginx_mismatch(self):
        """The case that prompted #654: nginx left on the default port."""
        self.install(cds_port=55152, logger_manager=':55152', django_nginx=8766,
                     react_nginx=8766, react_env=55152)
        output = self.run_script('status')

        self.assertIn('WARNING: the CachedDataServer listens on port 55152', output)
        self.assertIn(self.supervisor_file('cached_data'), output)
        self.assertIn('Django UI nginx proxy for /cds-ws: 8766', output)
        self.assertIn('React UI nginx proxy for /cds-ws: 8766', output)
        self.assertIn(os.path.join(self.root, 'django_gui', 'openrvdas_nginx.conf'),
                      output)
        self.assertIn('Unexpected response code: 502', output)
        self.assertIn('change each port listed above to 55152', output)
        # The ones that are right aren't listed
        self.assertNotIn('logger_manager --data_server_websocket:', output)
        self.assertNotIn('React backend CACHED_DATA_SERVER_PORT:', output)

    def test_other_mismatches(self):
        self.install(cds_port=8766, logger_manager='localhost:9000',
                     django_nginx=8766, react_nginx=8766, react_env=55152)
        output = self.run_script('status')

        self.assertIn('WARNING: the CachedDataServer listens on port 8766', output)
        self.assertIn('logger_manager --data_server_websocket: 9000', output)
        self.assertIn('React backend CACHED_DATA_SERVER_PORT: 55152', output)
        self.assertNotIn('nginx proxy for /cds-ws:', output)

    def test_env_file_secrets_are_not_shown(self):
        self.install(react_env=55152)
        output = self.run_script('status')
        self.assertIn('React backend CACHED_DATA_SERVER_PORT: 55152', output)
        self.assertNotIn('not-a-port', output)

    def test_ui_not_installed(self):
        """Files for a UI that was never installed aren't a mismatch."""
        self.install(react_nginx=None, react_env=None)
        self.assertNotIn(PORT_WARNING, self.run_script('status'))

    def test_no_cds_config(self):
        self.install(cds_port=None)
        output = self.run_script('status')
        self.assertIn('NOTE: could not find the CachedDataServer', output)
        self.assertNotIn(PORT_WARNING, output)

    def test_warning_shown_before_switching(self):
        self.install(django_nginx=9999)
        output = self.run_script('none', '--dry-run')
        self.assertIn('Django UI nginx proxy for /cds-ws: 9999', output)
        self.assertIn('--dry-run given; no changes made.', output)
        # The warning comes before the summary of what will change
        self.assertLess(output.index(PORT_WARNING), output.index('This will:'))


if __name__ == '__main__':
    unittest.main()
