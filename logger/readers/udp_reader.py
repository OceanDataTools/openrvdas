#!/usr/bin/env python3

import logging
import socket
import struct
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402

# The UDP header's `length` field sets a theoretical limit of 65,535 bytes
# (8-byte header + 65,527 bytes of data) for a UDP datagram.  Technically, IPV4
# or IPv6 headers use up some of that size, so actual maximum data sent per
# datagram is slightly less.
#
# UDP receivers should always request the max, though, because if you request
# less than what's on the wire, you get what you asked for and the rest gets
# tossed on the floor.  There's no built-in error detection/correction in UDP,
# so that would mess things up pretty good.
READ_BUFFER_SIZE = 65535


################################################################################
class UDPReader(Reader):
    """Read UDP packets from network."""
    ############################
    def __init__(self, port, source='', eol=None,
                 encoding='utf-8', encoding_errors='ignore'):
        """
        ```
        port         Port to listen to for packets

        source       If specified, multicast group id to listen for

        eol          If not specified, assume one record per network packet.  If
                     specified, buffer network reads until the eol
                     character has been seen, and return the entire record
                     at once, retaining everything after the eol for the
                     start of the subsequent record. If multiple eol characters
                     are encountered in a packet, split the packet and return
                     the first of them, buffering the remainder for subsequent
                     calls.

        encoding - 'utf-8' by default. If empty or None, do not attempt any decoding
                and return raw bytes. Other possible encodings are listed in online
                documentation here:
                https://docs.python.org/3/library/codecs.html#standard-encodings

        encoding_errors - 'ignore' by default. Other error strategies are 'strict',
                'replace', and 'backslashreplace', described here:
                https://docs.python.org/3/howto/unicode.html#encodings

        ```
        """
        super().__init__(encoding=encoding,
                         encoding_errors=encoding_errors)

        # 'eol' comes in as a (probably escaped) string. We need to
        # unescape it, which means converting to bytes and back.
        if eol is not None:
            eol = self._unescape_str(eol)
        self.eol = eol

        # Where we'll aggregate incomplete records if an eol char is specified
        self.record_buffer = ''

        self.socket = socket.socket(family=socket.AF_INET,
                                    type=socket.SOCK_DGRAM,
                                    proto=socket.IPPROTO_UDP)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)

        # If source is specified, subscribe to it as a multicast group
        if source:
            mreq = struct.pack("4sl", socket.inet_aton(source), socket.INADDR_ANY)
            self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        try:  # Raspbian doesn't recognize SO_REUSEPORT
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
        except AttributeError:
            logging.warning('Unable to set socket REUSEPORT; may be unsupported.')

        # If source is empty, we're listening for broadcasts, otherwise
        # listening for multicast on IP 'source'
        self.socket.bind((source, port))

    ############################
    def read(self):
        """
        Read the next UDP packet.
        """
        # If no eol character/string specified, just read a packet and
        # return it as the next record.
        if not self.eol:
            try:
                record = self.socket.recv(READ_BUFFER_SIZE)
            except OSError as e:
                logging.error('UDPReader error: %s', str(e))
                return None
            logging.debug('UDPReader.read() received %d bytes', len(record))
            return self._decode_bytes(record)

        # If an eol character/string has been specified, we may have to
        # loop our reads until we see an eol.
        while True:
            eol_pos = self.record_buffer.find(self.eol)
            if eol_pos > -1:
                # We have an eol string somewhere in our buffer. Return
                # everything up to it.
                record_end = eol_pos + len(self.eol)
                record = self.record_buffer[0:record_end-1]
                logging.debug('UDPReader found eol; returning record')
                self.record_buffer = self.record_buffer[record_end:]
                return record

            # If no eol string, read, append, and try again.
            record = self.socket.recv(READ_BUFFER_SIZE)
            logging.debug('UDPReader.read() received %d bytes', len(record))
            if record:
                self.record_buffer += self._decode_bytes(record)
