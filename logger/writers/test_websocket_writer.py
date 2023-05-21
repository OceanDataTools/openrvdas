#!/usr/bin/env python3

import logging
import sys
import threading
import time

import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.websocket_writer import WebsocketWriter
from logger.readers.websocket_reader import WebsocketReader

class WebsocketWriterTest(unittest.TestCase):

    # Method to run in separate thread to run WebsocketReader
    def _run_writer(self, port, records, cert_file=None, key_file=None):
        writer = WebsocketWriter(port=port, cert_file=cert_file, key_file=key_file)

        while not writer.client_map:
            time.sleep(0.1)
        logging.debug(f'writer got client')

        for record in records:
            logging.debug(f'writer writing {record}')
            writer.write(record)
            time.sleep(0.1)
        logging.debug(f'writer thread exiting')

    def test_read(self):
        uri = 'ws://localhost:8080'
        records = ["Hello, world!", "Goodbye, world!"]
        writer_thread = threading.Thread(target=self._run_writer,
                                            args=(8080, records),
                                            daemon=True)
        writer_thread.start()

        reader = WebsocketReader(uri=uri)
        for record in records:
            logging.debug(f'reader expecting {record}')
            received = reader.read()
            self.assertEqual(received, record)
            logging.debug(f'reader got {received}')
        logging.debug(f'reader exiting')

        writer_thread.join()
        logging.debug(f'writer thread joined')

    def test_read_ssl(self):
        uri = 'wss://localhost:8081'
        records = ["Hello, world!", "Goodbye, world!"]
        cert_file = dirname(realpath(__file__)) + '/test.crt'
        key_file = dirname(realpath(__file__)) + '/test.key'
        writer_thread = threading.Thread(target=self._run_writer,
                                            args=(8081, records, cert_file, key_file),
                                            daemon=True)
        writer_thread.start()

        reader = WebsocketReader(uri=uri)
        reader1 = WebsocketReader(uri=uri)

        for record in records:
            logging.debug(f'reader expecting {record}')
            received = reader.read()
            self.assertEqual(received, record)
            logging.debug(f'reader got {received}')
        logging.debug(f'reader exiting')

        writer_thread.join()
        logging.debug(f'writer thread joined')

if __name__ == "__main__":
    unittest.main()
