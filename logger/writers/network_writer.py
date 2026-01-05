#!/usr/bin/env python3

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.writer import Writer  # noqa: E402


class NetworkWriter(Writer):
    def __init__(self, network, num_retry=2, eol='',
                 encoding='utf-8', encoding_errors='ignore'):
        super().__init__(**kwargs)
        logging.error("NetworkWriter has been replaced by TCPWriter and UDPWriter")

    def write(self, record):
        logging.error("not writing anything: NetworkWriter has been replaced "
                      "by TCPWriter and UDPWriter")
