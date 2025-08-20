#!/usr/bin/env python3

import sys
import json
import logging
import urllib
from typing import Union
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.writer import Writer  # noqa: E402

class SealogWriter(Writer):
    """Submit Sealog event dicts to a Sealog Server API."""

    def __init__(self, url: str, token:str, quiet: bool=False):
        super().__init__(quiet=quiet)

        self.url = url
        self.token = token

        self.test_api_connectivity()


    def test_api_connectivity(self) -> bool:
        """
        Test connectivity to a restricted API route using JWT authentication
        
        Returns:
            bool: True if request succeeds (HTTP 200), False otherwise.
        """
        req = urllib.request.Request(self.url + '/restricted')
        req.add_header("Authorization", f"Bearer {self.token}")

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    logging.info("Connection to Sealog Server successful")
                    return True
                else:
                    logging.error(f"Connection to Sealog Server failed: {response.status}")
                    return False
        except urllib.error.HTTPError as e:
            logging.error(f"HTTP error: {e.code} {e.reason}")
            return False
        except urllib.error.URLError as e:
            logging.error(f"Connection error: {e.reason}")
            return False


    ############################
    def write(self, record: Union[dict, list]):
        """Submit dicts to Sealog Server
        Note: Assume record is a dict or list of dict.
        """

        if isinstance(record, list):
            for single_record in record:
                self.transform(single_record)
            return

        # Convert data dict to JSON bytes
        json_data = json.dumps(record).encode("utf-8")

        req = urllib.request.Request(self.url + '/api/v1/events', data=json_data, method="POST")
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 201:
                    logging.debug("POST successful")
                else:
                    logging.error(f"POST failed: {response.status}")
        except urllib.error.HTTPError as e:
            logging.error(f"HTTP error: {e.code} {e.reason}")
        except urllib.error.URLError as e:
            logging.error(f"Connection error: {e.reason}")
