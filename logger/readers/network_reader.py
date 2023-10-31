#!/usr/bin/env python3

import logging
import socket
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402


class NetworkReader(Reader):
    def __init__(self, network, eol='',
                 encoding='utf-8', encoding_errors='ignore'):
        super().__init__(encoding=encoding,
                         encoding_errors=encoding_errors)
        logging.error("NetworkReader has been replaced by TCPReader and UDPReader")

    def read(self):
        logging.error("not reading anything: NetworkReader has been replaced by TCPReader and UDPReader")
