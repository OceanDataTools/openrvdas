#!/usr/bin/env python3

import sys
import time
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

sys.path.append('.')
from logger.readers.http_reader import HTTPReader  # noqa: E402


class TestHTTPReader(unittest.TestCase):

    def setUp(self):
        self.urlopen_patcher = patch(
            "logger.readers.http_reader.urlopen"
        )
        self.mock_urlopen = self.urlopen_patcher.start()

        # Default mock response
        self.mock_response = MagicMock()
        self.mock_response.status = 200
        self.mock_response.read.return_value = b"Hello, HTTP!"
        self.mock_response.__enter__.return_value = self.mock_response
        self.mock_response.__exit__.return_value = None

        # HEAD verification response
        self.mock_head_response = MagicMock()
        self.mock_head_response.status = 200
        self.mock_head_response.__enter__.return_value = self.mock_head_response
        self.mock_head_response.__exit__.return_value = None

        def urlopen_side_effect(*args, **kwargs):
            req = args[0]
            method = getattr(req, "method", "GET")
            if method == "HEAD":
                return self.mock_head_response
            return self.mock_response

        self.mock_urlopen.side_effect = urlopen_side_effect

    def tearDown(self):
        self.urlopen_patcher.stop()

    def test_get_request_returns_text(self):
        reader = HTTPReader(
            url="http://example.com",
            method="get",
            encoding="utf-8",
            interval=0.0,
        )

        result = reader.read()
        self.assertEqual(result, "Hello, HTTP!")

        # HEAD + GET
        self.assertEqual(self.mock_urlopen.call_count, 2)

    def test_post_request_with_payload(self):
        payload = {"key": "value"}

        reader = HTTPReader(
            url="http://example.com",
            method="post",
            payload=payload,
            encoding="utf-8",
            interval=0.0,
        )

        # Update read response for POST
        self.mock_response.read.return_value = b"POST OK"

        result = reader.read()
        self.assertEqual(result, "POST OK")

        self.assertEqual(self.mock_urlopen.call_count, 2)

    def test_read_returns_bytes_when_encoding_none(self):
        reader = HTTPReader(
            url="http://example.com",
            method="get",
            encoding=None,
            interval=0.0,
        )

        result = reader.read()
        self.assertEqual(result, b"Hello, HTTP!")

    def test_headers_are_passed_through(self):
        headers = {"Authorization": "Bearer token"}

        reader = HTTPReader(
            url="http://example.com",
            method="get",
            headers=headers,
            interval=0.0,
        )

        reader.read()

        # Inspect the GET request
        _, kwargs = self.mock_urlopen.call_args
        request = self.mock_urlopen.call_args[0][0]

        self.assertEqual(request.headers["Authorization"], "Bearer token")

    def test_read_respects_interval(self):
        reader = HTTPReader(
            url="http://example.com",
            method="get",
            encoding="utf-8",
            interval=0.2,
        )

        start = time.monotonic()
        reader.read()
        reader.read()
        elapsed = time.monotonic() - start

        self.assertGreaterEqual(elapsed, 0.2)

    def test_invalid_method_raises_value_error(self):
        with self.assertRaises(ValueError):
            HTTPReader(url="http://example.com", method="put")

    def test_invalid_url_raises_value_error(self):
        with self.assertRaises(ValueError):
            HTTPReader(url="ftp://example.com", method="get")

    def test_verification_401_is_accepted(self):
        # HEAD returns 401 → should still verify
        http_error = HTTPError(
            url="http://example.com",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

        self.mock_urlopen.side_effect = [
            http_error,        # HEAD
            self.mock_response # GET
        ]

        reader = HTTPReader(
            url="http://example.com",
            method="get",
            interval=0.0,
        )

        result = reader.read()
        self.assertEqual(result, "Hello, HTTP!")

    def test_verification_404_fails(self):
        http_error = HTTPError(
            url="http://example.com",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

        self.mock_urlopen.side_effect = http_error

        reader = HTTPReader(
            url="http://example.com",
            method="get",
            interval=0.0,
        )

        result = reader.read()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
