#!/usr/bin/env python3

import json
import logging
import socket
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.writer import Writer  # noqa: E402


# FIXME: implement tcp, remove udp entirely, maybe rename TCPWriter?  could
#        make an issue for this.
#
class TCPWriter(Writer):
    """Write TCP packtes to network."""

    def __init__(self, port, destination,
                 num_retry=2, warning_limit=5, eol='',
                 encoding='utf-8', encoding_errors='ignore'):
        """
        Write records to a TCP network socket.

        ```
        port         Port to which packets should be sent

        destination  The destination to send TCP packets to.  Can be resolvable hostname
                     or valid IP address.

        num_retry    Number of times to retry if write fails.

        warning_limit  Number of times the writer gives up on writing a message
                     (without any intervening successes) before it gives up complaining
                     about failures.

        eol          If specified, an end of line string to append to record
                     before sending

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

        self.num_retry = num_retry
        self.warning_limit = warning_limit
        self.num_warnings = 0

        # 'eol' comes in as a (probably escaped) string. We need to
        # unescape it, which means converting to bytes and back.
        if eol is not None and self.encoding:
            eol = self._unescape_str(eol)
        self.eol = eol

        # do name resolution once in the constructor
        #
        # NOTE: This means the hostname must be valid when we start, otherwise
        #       the config_check code will puke.  That's fine.  The alternative
        #       is we let name resolution happen while we're running, but then
        #       each failed lookup is going to block our write() routine for a
        #       few seconds - not good.
        #
        # NOTE: This also catches specifying impropperly formatted IP
        #       addresses.  The only way through gethostbyname() w/out throwing
        #       an exception is to provide a valid hostname or IP address.
        #       Propperly formatted IPs just get returned.
        #
        self.destination = socket.gethostbyname(destination)

        # make sure port gets stored as an int, even if passed in as a string
        self.port = int(port)

        # Try opening the socket
        self.socket = self._open_socket()

    ############################
    def _open_socket(self):
        """Try to open and return the network socket.
        """
        this_socket = socket.socket(family=socket.AF_INET,
                                    type=socket.SOCK_STREAM,
                                    proto=socket.IPPROTO_TCP)

        # FIXME: double-check i don't need to do anything else in here...
        #        recv-side needs to do a lot (bind, accept), but i think
        #        send-side just needs to connect

        # Try connecting
        try:
            this_socket.connect((self.destination, self.port))
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

        # Append eol if configured
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
        while num_tries <= self.num_retry and bytes_sent < rec_len:
            try:
                bytes_sent = self.socket.send(self._encode_str(record))
                if self.num_warnings == self.warning_limit:
                    logging.info('TCPWriter.write() succeeded in writing after series of'
                                 'failures; resetting warnings.')
                    self.num_warnings = 0 # we've succeeded

            except OSError as e:
                if self.num_warnings < self.warning_limit:
                    logging.error('TCPWriter error: %s:%d: %s', self.destination, self.port, str(e))
                    logging.error('TCPWriter record: %s', record)
                    self.num_warnings += 1
                    if self.num_warnings == self.warning_limit:
                        logging.error('TCPWriter.write() - muting errors')
            num_tries += 1

        logging.debug('TCPWriter.write() wrote %d/%d bytes after %d tries',
                      bytes_sent, rec_len, num_tries)
