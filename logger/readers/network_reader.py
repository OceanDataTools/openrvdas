#!/usr/bin/env python3

import logging
import socket
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402
from logger.utils.formats import Text  # noqa: E402

READ_BUFFER_SIZE = 4096  # max number of characters to read in one call


################################################################################
# Read to the specified file. If filename is empty, read to stdout.
class NetworkReader(Reader):
    """
    Read text records from a network socket.

    NOTE: tcp is nominally implemented, but DOES NOT WORK!

    TODO: code won't handle records that are larger than 4K right now,
    which, if we start getting into Toby Martin's Total Metadata Ingestion
    (TMI), may not be enough. We'll need to implement something that will
    aggregate recv()'s and know when it's got an entire record?
    """
    ############################

    def __init__(self, network, eol=None, read_buffer_size=READ_BUFFER_SIZE,
                 encoding='utf-8', encoding_errors='ignore'):
        """
        ```
        network      Network address to read, in host:port format (e.g.
                     'rvdas:6202'). If host is omitted (e.g. ':6202'),
                     read via UDP on specified port.

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
        super().__init__(output_format=Text,
                         encoding=encoding,
                         encoding_errors=encoding_errors)

        self.network = network
        if eol is not None:
            eol = self._unescape_str(eol)
        self.eol = eol
        self.read_buffer_size = read_buffer_size

        # Where we'll aggregate incomplete records if an eol char is specified
        self.record_buffer = ''

        if network.find(':') == -1:
            raise ValueError('NetworkReader network argument must be in \'host:port\''
                             ' or \':port\' format. Found "%s"' % network)
        (host, port) = network.split(':')
        port = int(port)

        # TCP if host is specified
        if host:
            self.socket = socket.socket(family=socket.AF_INET,
                                        type=socket.SOCK_STREAM,
                                        proto=socket.IPPROTO_TCP)
            # Should this be bind()?
            self.socket.connect((host, port))

        # UDP broadcast if no host specified. Note that there's some
        # dodginess I don't understand about networks: if '<broadcast>' is
        # specified, socket tries to send on *all* interfaces. if '' is
        # specified, it tries to send on *any* interface.
        else:
            host = ''  # special code for broadcast
            self.socket = socket.socket(family=socket.AF_INET,
                                        type=socket.SOCK_DGRAM,
                                        proto=socket.IPPROTO_UDP)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
            try:  # Raspbian doesn't recognize SO_REUSEPORT
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
            except AttributeError:
                logging.warning('Unable to set socket REUSEPORT; system may not support it.')
            self.socket.bind((host, port))

    ############################
    def read(self):
        """
        Read the next network packet.
        """
        # If no eol character/string specified, just read a packet and
        # return it as the next record.
        if not self.eol:
            record = self.socket.recv(self.read_buffer_size)
            logging.debug('NetworkReader.read() received %d bytes', len(record))
            return self._decode_bytes(record)

        # If an eol character/string has been specified, we may have to
        # loop our reads until we see an eol.
        while True:
            eol_pos = self.record_buffer.rfind(self.eol)
            if eol_pos > -1:
                logging.debug('NetworkReader found eol; returning record')

                # We have an eol string somewhere in our buffer. Extract
                # everything up to the last eol and split up by eol's.
                record_end = eol_pos + len(self.eol)
                record = self.record_buffer[0:eol_pos].split(self.eol)
                self.record_buffer = self.record_buffer[record_end:]

                # If we only have one record in list, return it as a string,
                # otherwise return as list of strings.
                if len(record) == 1:
                    record = record[0]
                return record

            # If no eol string, read, append, and try again.
            record = self.socket.recv(self.read_buffer_size)
            logging.debug('NetworkReader.read() received %d bytes', len(record))
            if record:
                self.record_buffer += self._decode_bytes(record)
