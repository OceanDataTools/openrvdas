#!/usr/bin/env python3
import threading
import sys
import time
import logging
import requests

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))
from logger.readers.reader import Reader  # noqa: E402
from logger.utils.formats import Text  # noqa: E402


################################################################################
# Read to the specified file. If filename is empty, read to stdout.
class HTTPReader(Reader):  # noqa: R0913
    """
    Read data from a URL at a set interval.
    """

    _ALLOWED_METHODS = {
        "get": "get",
        "post": "post"
    }

    ############################
    def __init__(self, url: str, method: str = 'get',  # noqa: R0902
                 headers: dict | None = None,payload: dict | None = None,
                 polling_rate: float = 5.0, timeout: float = 2.0,
                 encoding='utf-8', encoding_errors='ignore'):
        """
        ```
        url      Network url to read, in protocol://host:port format (e.g.
                     'https://example.com' 'http://example.com:8000').

        method  type of http request

        headers  Headers to set for the request

        payload  Payload to set for the request. Only applicable for POST/PATCH requests

        polling_rate Seconds between update requests to MOXA Device

        timeout      Max time to wait for device to respond.

        encoding - 'utf-8' by default. If empty or None, do not attempt any decoding
                and return raw bytes. Other possible encodings are listed in online
                documentation here:
                https://docs.python.org/3/library/codecs.html#standard-encodings

        encoding_errors - 'ignore' by default. Other error strategies are 'strict',
                'replace', and 'backslashreplace', described here:
                https://docs.python.org/3/howto/unicode.html#encodings
        ```
        """
        super().__init__(output_format=Text,
                         encoding=encoding,
                         encoding_errors=encoding_errors)

        self.url = self._validate_url(url)
        self.method = self._validate_method(method)
        self.headers = headers or {}
        self.payload = payload
        self.polling_rate = polling_rate
        self.timeout = timeout

        self._read_lock = threading.Lock()
        self._verified = False

    ############################
    def _verify_url(self):
        """Check URL reachability on first read."""
        if self._verified:
            return

        try:
            res = requests.head(
                self.url,
                allow_redirects=True,
                timeout=self.timeout
            )

            if res.status_code < 400:
                self._verified = True
                return

            # Some servers block or mishandle HEAD
            if res.status_code in (401, 403, 405):
                res = requests.get(
                    self.url,
                    allow_redirects=True,
                    stream=True,   # do not download body
                    timeout=self.timeout
                )
                if res.status_code < 400:
                    self._verified = True
                    return

            raise ValueError(f"invalid url={self.url}")

        except requests.RequestException:
            raise ValueError(f"invalid url={self.url}")

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
    def _make_request(self) -> requests.Response:
        """Perform a single HTTP request with proper method and payload."""
        func = getattr(requests, self.method)
        headers = dict(self.headers)
        kwargs = {
            "url": self.url,
            "headers": headers,
            "timeout": self.timeout,
            "allow_redirects": True,
        }

        if self.method == "post" and self.payload is not None:
            kwargs["json"] = self.payload

        return func(**kwargs)

    def _parse_response(self, response: requests.Response) -> str | bytes:
        """Decode response according to encoding settings."""
        response.raise_for_status()  # raises for HTTP 4xx/5xx
        if self.encoding:
            return response.content.decode(
                self.encoding, errors=self.encoding_errors
            )
        return response.content

    ############################
    def read(self) -> str | bytes:
        """
        Poll the HTTP endpoint and return one reading.
        This method blocks until the next polling interval.
        """

        start = time.monotonic()

        try:
            with self._read_lock:
                self._verify_url()
                res = self._make_request()
                record = self._parse_response(res)
        except requests.RequestException as exc:
            self._verified = False
            logging.warning("HTTP read failed: %s %s", self.method, self.url)
            raise RuntimeError(f"HTTP read failed: {exc}") from exc

        elapsed = time.monotonic() - start
        sleep_time = self.polling_rate - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

        return record
