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

    def __init__(self, destination, port,
                 num_retry=2, warning_limit=5, eol='',
                 encoding='utf-8', encoding_errors='ignore'):
        """
        Write records to a TCP network socket.

        ```
        destination  The destination to send TCP packets to.  Can be resolvable hostname
                     or valid IP address.

        port         Port to which packets should be sent

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

        # socket gets initialized on-demand in write()
        #
        # NOTE: Since connect() can actually fail w/ a TCP socket, we don't try
        #       that here.  Let's just do safe things.
        #
        self.socket = None

    ############################
    def _open_socket(self):
        """Do socket prep so we're ready to write().  Returns socket object or None on
        failure.
        """
        this_socket = socket.socket(family=socket.AF_INET,
                                    type=socket.SOCK_STREAM,
                                    proto=socket.IPPROTO_TCP)
        this_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        try:  # Raspbian doesn't recognize SO_REUSEPORT
            this_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
        except AttributeError:
            logging.warning('Unable to set socket REUSEPORT; may be unsupported')

        # Try connecting
        try:
            this_socket.connect((self.destination, self.port))
        except OSError as e:
            if self.num_warnings < self.warning_limit:
                logging.error('Unable to connect to %s:%d: %s', self.destination, self.port, e)
                self.num_warnings += 1
                if self.num_warnings == self.warning_limit:
                    logging.error('TCPWriter._open_socket() - muting errors')
            return None

        # success, reset warning counter
        if self.num_warnings == self.warning_limit:
            logging.info('TCPWriter._open_socket() successfully connected after a series of '
                         'failures; restting warnings.')
        self.num_warnings = 0
        return this_socket

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

        # NOTE: Unlike UDP socket, which really only can detect failure during
        #       send() (and even then only very poorly), a TCP connect() can
        #       fail, so we need to track attempts to connect in order to honor
        #       `num_retry` on a disconnected socket.
        #
        #       We also need to tear down and start over with a fresh connect()
        #       if send() fails.
        #
        num_tries = 0
        bytes_sent = 0
        rec_len = len(record)
        while num_tries <= self.num_retry and bytes_sent < rec_len:
            num_tries += 1
            # attempt to connect socket if needed, up to `num_tries` times
            if not self.socket:
                self.socket = self._open_socket()
            if not self.socket:
                # no need for further error messages, _open_socket() will have
                # already complained sufficiently
                continue

            # we're connected, try sending
            try:
                bytes_sent = self.socket.send(self._encode_str(record))
            except OSError as e:
                # send failed, we need to disconnect and start over
                #
                # NOTE: In order to get this far, we have to have successfully
                #       connected, which means we JUST reset self.num_warnings
                #
                logging.error('TCPWriter: send() error: %s:%d: %s', self.destination, self.port, str(e))
                self.num_warnings += 1
                self.socket = None
                continue

            # check to see if we really wrote it all
            if bytes_sent < rec_len:
                logging.warning('TCPWriter: send() did not send the whole record: '
                                'bytes_sent=%d, rec_len=%d', bytes_sent, rec_len)

        logging.debug('TCPWriter.write() wrote %d/%d bytes after %d tries',
                      bytes_sent, rec_len, num_tries)