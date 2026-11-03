#!/usr/bin/env python3
"""
Check that CachedDataServer only installs its HTTP-route handler when the
websockets library will call it with the signature it expects.

The handler added in #537 takes (connection, request) and reads
request.headers - the asyncio server's process_request() signature. The
legacy server calls process_request(path, request_headers) instead, passing
a Headers object where the handler expects a request, so installing the
handler there makes every handshake fail with

    AttributeError: 'Headers' object has no attribute 'headers'

and the client sees 500 Internal Server Error.

Importing websockets.http11 does not distinguish the two: it has existed
since websockets 10, while websockets.serve only became the asyncio
implementation in 14.0. That matters on Python 3.8 (Ubuntu 20), where
websockets >= 14 cannot be installed at all.

These tests need no socket, so unlike test_cached_data_server.py they run
in restricted environments.

Run with: python -m pytest test/server/test_cached_data_server_ws_compat.py
"""

import importlib
import logging
import unittest
from unittest.mock import patch

import websockets  # noqa: E402

import server.cached_data_server as cds  # noqa: E402


##############################################################################
class TestWebsocketsServerCompat(unittest.TestCase):

    @staticmethod
    def _flag_with_serve_from(module_name):
        """Reload cached_data_server with websockets.serve pretending to come
        from module_name, and report the flag it computes."""
        def fake_serve(*args, **kwargs):
            raise AssertionError('fake serve should never be called')
        fake_serve.__module__ = module_name

        with patch.object(websockets, 'serve', fake_serve):
            reloaded = importlib.reload(cds)
            return reloaded._WEBSOCKETS_HAS_HTTP11

    ############################
    def tearDown(self):
        # Leave the module as the real environment has it.
        importlib.reload(cds)

    ############################
    def test_handler_disabled_on_legacy_server(self):
        """The regression: websockets 13.x and older."""
        self.assertFalse(
            self._flag_with_serve_from('websockets.legacy.server'),
            'HTTP-route handler must not be installed on the legacy server; '
            'it would make every WebSocket handshake return 500')

    ############################
    def test_handler_enabled_on_asyncio_server(self):
        """websockets 14+ calls process_request(connection, request)."""
        self.assertTrue(
            self._flag_with_serve_from('websockets.asyncio.server'),
            'HTTP-route handler should be installed on the asyncio server')

    ############################
    def test_flag_matches_installed_websockets(self):
        """Whatever is actually installed here, the flag must agree with it."""
        expected = websockets.serve.__module__.startswith('websockets.asyncio')
        self.assertEqual(
            cds._WEBSOCKETS_HAS_HTTP11, expected,
            f'websockets.serve comes from {websockets.serve.__module__}, '
            f'so _WEBSOCKETS_HAS_HTTP11 should be {expected}')


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
