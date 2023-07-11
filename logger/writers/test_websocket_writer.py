#!/usr/bin/env python3

import logging
import sys
import threading
import time

import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.websocket_writer import WebsocketWriter  # noqa: E402
from logger.readers.websocket_reader import WebsocketReader  # noqa: E402


class WebsocketWriterTest(unittest.TestCase):

    # Method to run in separate thread to run WebsocketReader
    def _run_writer(self, uri, records, cert_file=None, key_file=None):
        writer = WebsocketWriter(uri=uri, cert_file=cert_file, key_file=key_file)

        while not writer.client_map:
            time.sleep(0.1)
        logging.debug('writer got client')

        for record in records:
            logging.debug(f'writer writing {record}')
            writer.write(record)
            time.sleep(0.1)
        logging.debug('writer thread exiting')

    def test_read(self):
        uri = 'ws://localhost:8080'
        records = ["Hello, world!", "Goodbye, world!"]
        writer_thread = threading.Thread(target=self._run_writer,
                                         args=(uri, records),
                                         daemon=True)
        writer_thread.start()

        reader = WebsocketReader(uri=uri)
        for record in records:
            logging.debug(f'reader expecting {record}')
            received = reader.read()
            self.assertEqual(received, record)
            logging.debug(f'reader got {received}')
        logging.debug('reader exiting')

        writer_thread.join()
        logging.debug('writer thread joined')

    def test_read_ssl(self):
        uri = 'wss://localhost:8081'
        records = ["Hello, world!", "Goodbye, world!"]
        cert_file = dirname(dirname(realpath(__file__))) + '/utils/test.crt'
        key_file = dirname(dirname(realpath(__file__))) + '/utils/test.key'
        writer_thread = threading.Thread(target=self._run_writer,
                                         args=(uri, records, cert_file, key_file),
                                         daemon=True)
        writer_thread.start()

        reader = WebsocketReader(uri=uri)
        for record in records:
            logging.debug(f'reader expecting {record}')
            received = reader.read()
            self.assertEqual(received, record)
            logging.debug(f'reader got {received}')
        logging.debug('reader exiting')

        writer_thread.join()
        logging.debug('writer thread joined')


if __name__ == "__main__":
    unittest.main()
