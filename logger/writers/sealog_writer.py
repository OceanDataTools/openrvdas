#!/usr/bin/env python3

import sys
import json
import logging
import urllib
from typing import Union
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa:E402
from logger.utils.read_config import read_config  # noqa:E402
from logger.utils.sealog_event import SealogEvent, to_event  # noqa:E402
from logger.writers.writer import Writer  # noqa: E402

class SealogWriter(Writer):
    """Submit Sealog event dicts to a Sealog Server API.

    url    - URL to Sealog Server, i.e. http://<ip_addr>:8000/sealog-server

    token  - Java Web Token (JWT) authorized to submit new events to the
             Sealog Server API 

    config_file  - Path to a YAML configuration file specifying:
                   `data_id` to determine which set of rules to apply
                   `event_value` (optional): default event value for the record.
                   `event_author` (optional): author string to include in the event.
                   `event_free_text` (optional): free text string for the event.
                   `field_map` (optional): mapping of input record field names to event option names.
                   `_default` (optional): fallback configuration applied if the record's `data_id` is not found.

    Sample configuration file:
    ---
    qinsy:
        event_value: LOGGING_STATUS
        event_author: "qinsy"
        event_free_text: ""
        field_map:
            status: status
            filename: filename

    _default:
        event_value: UNKNOWN
        event_free_text: ""
        field_map: null


    quiet   - suppress warning messages

    """

    def __init__(self, url: str, token: str, config_file: str, quiet: bool=False):
        super().__init__(quiet=quiet)

        self.url = url
        self.token = token

        try:
            self.configs = read_config(config_file)
            logging.info('Loaded sealog config file: %s', pprint.pformat(self.configs))
        except Exception as err:
            logging.error("Could not find or could not process config file.  All records will be ignored.")
            pass

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
    def write(self, record: Union[DASRecord, SealogEvent, list]):
        """Submit dicts to Sealog Server
        Note: Assume record is a dict or list of dict.
        """

        if isinstance(record, list):
            for single_record in record:
                self.transform(single_record)
            return

        event = record if isinstance(record, SealogEvent) else to_event(record, self.configs) 

        json_data = event.as_json()

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
