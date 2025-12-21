#!/usr/bin/env python3

import sys
import time
import unittest
from unittest.mock import patch, MagicMock

sys.path.append('.')
from logger.readers.http_reader import HTTPReader  # noqa: E402

class TestHTTPReader(unittest.TestCase):
    def setUp(self):
        # Patch requests.get and requests.post
        self.get_patcher = patch('requests.get')
        self.post_patcher = patch('requests.post')

        self.mock_get = self.get_patcher.start()
        self.mock_post = self.post_patcher.start()

        # Mock GET response
        self.mock_get_response = MagicMock()
        self.mock_get_response.status_code = 200
        self.mock_get_response.content = b'Hello, HTTP!'
        self.mock_get.return_value = self.mock_get_response

        # Mock POST response
        self.mock_post_response = MagicMock()
        self.mock_post_response.status_code = 200
        self.mock_post_response.content = b'POST OK'
        self.mock_post.return_value = self.mock_post_response

    def tearDown(self):
        self.get_patcher.stop()
        self.post_patcher.stop()

    def test_get_request_returns_text(self):
        reader = HTTPReader(url='http://example.com', method='get',
                            encoding='utf-8', interval=0.1)
        result = reader.read()
        self.assertEqual(result, 'Hello, HTTP!')
        self.mock_get.assert_called_once_with(
            url='http://example.com',
            headers={},
            timeout=2.0,
            allow_redirects=True
        )

    def test_post_request_with_payload(self):
        payload = {'key': 'value'}
        reader = HTTPReader(url='http://example.com', method='post',
                            payload=payload, encoding='utf-8', interval=0.1)
        result = reader.read()
        self.assertEqual(result, 'POST OK')
        self.mock_post.assert_called_once_with(
            url='http://example.com',
            headers={},
            timeout=2.0,
            allow_redirects=True,
            json=payload
        )

    def test_read_returns_bytes_when_encoding_none(self):
        reader = HTTPReader(url='http://example.com', method='get', encoding=None, interval=0.1)
        result = reader.read()
        self.assertEqual(result, b'Hello, HTTP!')
        self.mock_get.assert_called_once()

    def test_headers_are_passed_through(self):
        headers = {'Authorization': 'Bearer token'}
        reader = HTTPReader(url='http://example.com', method='get',
                            headers=headers, interval=0.1)
        result = reader.read()
        self.assertEqual(result, 'Hello, HTTP!')
        self.mock_get.assert_called_once_with(
            url='http://example.com',
            headers=headers,
            timeout=2.0,
            allow_redirects=True
        )

    def test_read_respects_interval(self):
        reader = HTTPReader(url='http://example.com', method='get', encoding='utf-8',
                            interval=0.2)
        start = time.monotonic()
        reader.read()
        reader.read()
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.2)

    def test_invalid_method_raises_value_error(self):
        with self.assertRaises(ValueError):
            HTTPReader(url='http://example.com', method='put')

    def test_invalid_url_raises_value_error(self):
        with self.assertRaises(ValueError):
            HTTPReader(url='ftp://example.com', method='get')


if __name__ == '__main__':
    unittest.main()
