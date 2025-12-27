#!/usr/bin/env python3
"""
```
HTTPReader
==========

This module defines the :class:`HTTPReader`, a polling reader for retrieving
data from HTTP or HTTPS endpoints at a fixed interval.

The reader performs periodic HTTP GET or POST requests to a configured URL,
optionally including headers and a JSON payload. Responses are returned either
as decoded text or raw bytes, depending on the encoding configuration.

Key features
------------
- Supports HTTP GET and POST methods
- Configurable request headers and JSON payloads
- Enforces a minimum polling interval between requests
- Thread-safe access using an internal lock
- Optional URL verification on first read
- Supports decoded text output or raw byte output
- Integrates with the OpenRVDAS Reader framework

Typical usage
-------------
Example usage with a GET request:

    reader = HTTPReader(
        url="https://example.com/data",
        interval=10
    )

    record = reader.read()

Example usage with a POST request and JSON payload:

    reader = HTTPReader(
        url="https://example.com/api",
        method="post",
        headers={"Authorization": "Bearer TOKEN"},
        payload={"sensor": "temp"},
        interval=5
    )

    record = reader.read()

Output behavior
---------------
- If ``encoding`` is set (default: ``'utf-8'``), responses are decoded into
  strings using the specified encoding and error-handling strategy.
- If ``encoding`` is ``None`` or empty, raw response bytes are returned.
- On failure, ``read()`` returns ``None``.

Error handling
--------------
- On the first read, the reader verifies that the configured URL is reachable.
  URL verification fails if:
  - The server returns HTTP 404 (resource not found), or
  - The server returns any HTTP status code >= 500, or
  - A network or request error occurs (e.g., timeout, DNS failure).
- HTTP 401, 403, and 405 responses are treated as valid during verification,
  since they indicate a reachable endpoint.
- If URL verification fails, ``read()`` returns ``None``.
- During normal operation, HTTP 4xx or 5xx responses and network errors are
  treated as read failures, reset URL verification, and cause ``read()``
  to return ``None``.

Thread safety
-------------
All calls to ``read()`` are protected by an internal lock, making this reader
safe for use in multi-threaded environments.

```
"""

import threading
import sys
import time
import logging
import json

from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))
from logger.readers.reader import Reader  # noqa: E402

################################################################################
class HTTPReader(Reader):  # noqa: R0913
    """
    Read data from a URL at a set interval.
    """

    _ALLOWED_METHODS = {"get", "post"}

    ############################
    def __init__(self, url: str, method: str = 'get',  # noqa: R0902
                 headers: dict | None = None, payload: dict | None = None,
                 interval: float = 5.0, timeout: float = 2.0,
                 encoding: str | None = 'utf-8',
                 encoding_errors: str = 'ignore',
    ):
        """
        ```
        url - Network url to read, in protocol://host:port format (e.g.
              'https://example.com' 'http://example.com:8000').

        method - type of http request

        headers - Headers to set for the request

        payload - Payload to set for the request. Only applicable for
                  POST requests

        interval - Seconds between update requests, must be >=0

        timeout - Max time to wait for device to respond AND read the response.

        encoding - 'utf-8' by default. If empty or None, do not attempt any
                decoding and return raw bytes. Other possible encodings are
                listed in online documentation here:
                https://docs.python.org/3/library/codecs.html#standard-encodings

        encoding_errors - 'ignore' by default. Other error strategies are
                'strict', 'replace', and 'backslashreplace', described here:
                https://docs.python.org/3/howto/unicode.html#encodings
        ```
        """
        super().__init__(encoding=encoding,
                         encoding_errors=encoding_errors)

        if interval < 0:
            raise ValueError('Interval must be greater or equal to zero')

        self.url = self._validate_url(url)
        self.method = self._validate_method(method)
        self.headers = headers or {}
        self.payload = payload
        self.interval = interval
        self.timeout = timeout

        self._read_lock = threading.Lock()
        self._verified = False
        self._next_read_time = 0.0

    ############################
    def _verify_url(self):
        """Check URL reachability on first read."""
        if self._verified:
            return

        def _check_status(code: int):
            if code == 404 or code >= 500:
                raise ValueError(
                    f"invalid url: {self.url}; return code: {code}"
                )

        try:
            req = Request(self.url, method="HEAD", headers=self.headers)
            with urlopen(req, timeout=self.timeout) as resp:
                _check_status(resp.status)
                self._verified = True
                return

        except HTTPError as exc:
            # Some servers block or mishandle HEAD
            _check_status(exc.code)
            self._verified = True
            return

        except URLError:
            pass

        # Fallback to GET (do not explicitly read body)
        try:
            req = Request(self.url, method="GET", headers=self.headers)
            with urlopen(req, timeout=self.timeout) as resp:
                _check_status(resp.status)
                self._verified = True
                return

        except (HTTPError, URLError) as exc:
            raise ValueError(f"invalid url: {self.url}, {exc}")

    ############################
    def _validate_url(self, url: str) -> str:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"Invalid URL scheme: {url}")
        if len(url.split("://")[-1]) == 0:
            raise ValueError(f"Invalid URL: {url}")
        return url

    ############################
    def _validate_method(self, method: str) -> str:
        method = method.lower()
        if method not in self._ALLOWED_METHODS:
            raise ValueError(f"Unsupported HTTP method: {method}")
        return method

    ############################
    def _make_request(self):
        """Perform a single HTTP request."""
        headers = dict(self.headers)
        data = None

        if self.method == "post" and self.payload is not None:
            data = json.dumps(self.payload).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")

        req = Request(
            self.url,
            method=self.method.upper(),
            headers=headers,
            data=data,
        )

        return urlopen(req, timeout=self.timeout)

    ############################
    def _parse_response(self, response) -> str | bytes:
        data = response.read()
        if self.encoding:
            return data.decode(self.encoding, errors=self.encoding_errors)
        return data

    ############################
    def read(self) -> str | bytes | None:
        """
        Read from the HTTP endpoint. Returns immediately after the HTTP request
        completes, while enforcing a minimum interval between requests.
        """

        with self._read_lock:
            now = time.monotonic()

            # Enforce polling interval BEFORE the request
            if now < self._next_read_time:
                time.sleep(self._next_read_time - now)

            start = time.monotonic()

            try:
                self._verify_url()
                with self._make_request() as resp:
                    record = self._parse_response(resp)

            except (HTTPError, URLError, ValueError) as exc:
                self._verified = False
                logging.warning(
                    "HTTP read failed: %s %s: %s",
                    self.method,
                    self.url,
                    exc,
                )
                record = None

            finally:
                self._next_read_time = start + self.interval

            return record
