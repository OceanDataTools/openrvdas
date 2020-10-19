#!/usr/bin/env python3

import json
import logging
import socket
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.formats import Text  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402


class NetworkWriter(Writer):
    """Write to network."""

    def __init__(self, network, num_retry=2, eol=''):
        """
        Write text records to a network socket.

        NOTE: tcp is nominally implemented, but DOES NOT WORK!
        ```
        network      Network address to write, in host:port format (e.g.
                     'rvdas:6202'). If host is omitted (e.g. ':6202'),
                     broadcast via UDP on specified port.

        num_retry    Number of times to retry if write fails.

        eol          If specified, an end of line string to append to record
                     before sending
        ```
        """

        super().__init__(input_format=Text)

        if network.find(':') == -1:
            raise ValueError('NetworkWriter network argument must be in \'host:port\''
                             ' or \':port\' format. Found "%s"' % network)
        self.network = network
        self.num_retry = num_retry
        self.eol = eol

        # Try opening the socket
        self.socket = self._open_socket()

    ############################
    def _open_socket(self):
        """Try to open and return the network socket.
        """
        # TCP if host is specified
        (host, port) = self.network.split(':')
        port = int(port)
        if host:
            this_socket = socket.socket(family=socket.AF_INET,
                                        type=socket.SOCK_STREAM,
                                        proto=socket.IPPROTO_TCP)

        # UDP broadcast if no host specified. Note that there's some
        # dodginess I don't understand about networks: if '<broadcast>' is
        # specified, socket tries to send on *all* interfaces. if '' is
        # specified, it tries to send on *any* interface.
        else:
            this_socket = socket.socket(family=socket.AF_INET,
                                        type=socket.SOCK_DGRAM,
                                        proto=socket.IPPROTO_UDP)
            this_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
            try:  # Raspbian doesn't recognize SO_REUSEPORT
                this_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
            except AttributeError:
                logging.warning('Unable to set socket REUSEPORT; system may not support it.')

        # Try connecting
        try:
            this_socket.connect((host, port))  # should this be bind()?
            return this_socket
        except OSError as e:
            logging.warning('Unable to connect to %s: %s', self.network, e)
            return None

    ############################
    def write(self, record):
        """Write the record to the network."""
        # If we don't have a record, there's nothing to do
        if not record:
            return

        # If we've got a list, hope it's a list of records. Recurse,
        # calling write() on each of the list elements in order.
        if isinstance(record, list):
            for single_record in record:
                self.write(single_record)
            return

        # If record is not a string, try converting to JSON. If we don't know
        # how, throw a hail Mary and force it into str format
        if not isinstance(record, str):
            if type(record) in [int, float, bool, list, dict]:
                record = json.dumps(record)
            elif isinstance(record, DASRecord):
                record = record.as_json()
            else:
                record = str(record)
        if self.eol:
            record += self.eol

        # If socket isn't connected, try reconnecting. If we can't
        # reconnect, complain and return without writing.
        if not self.socket:
            self.socket = self._open_socket()
        if not self.socket:
            logging.error('Unable to write record to %s:%d',
                          self.destination, self.port)
            return

        num_tries = bytes_sent = 0
        rec_len = len(record)
        while num_tries < self.num_retry and bytes_sent < rec_len:
            try:
                bytes_sent = self.socket.send(record.encode('utf-8'))
            except OSError as e:
                logging.warning('Error while writing "%s": %s', record, str(e))
            num_tries += 1

        logging.debug('NetworkWriter.write() wrote %d/%d bytes after %d tries',
                      bytes_sent, rec_len, num_tries)
