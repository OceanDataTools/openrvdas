#!/usr/bin/env python3

import logging
import mmap
import socket
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402

# the size of each recv() call in read_to_eol()
#
# NOTE: Optimal value should be the system's page size, which is probably 4k.
#
READ_BUFFER_SIZE = mmap.PAGESIZE


################################################################################
class TCPReader(Reader):
    """ Read TCP packets from network."""
    ############################
    def __init__(self, interface=None, port=None, eol=None,
                 reuseaddr=True, reuseport=False,
                 encoding='utf-8', encoding_errors='ignore'):
        """
        ```
        interface    IP (or resolvable name) of interface to listen on.  None or ''
                     will listen on INADDR_ANY (all interfaces).

        port         Port to listen to for packets.  REQUIRED

        eol          If specified, buffer network reads until the `eol` sequence has
                     been seen, and return the entire record at once.  In other words,
                     present the user with a very UDP-ish 1 read gives you 1 whole
                     record feel, even though this is TCP.  If not specified, read()
                     calls must specify read sizes and it's up to the user to
                     control the TCP stream.

        reuseaddr    Specifies wether we set SO_REUSEADDR on the created socket.  This
                     is enabled by default (unlike TCPWriter, UDPWriter, or UDPReader)
                     specifically to avoid leftover TIME_WAIT sockets from
                     interferring with startup.

        reuseport    Specifies wether we set SO_REUSEPORT on the created socket.  If
                     you don't know you need this, don't enable it.

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

        if interface:
            # resolve once in constructor
            interface = socket.gethostbyname(interface)
        else:
            interface = ''
        self.interface = interface

        # make sure user passed in `port`
        #
        # NOTE: We want the order of the arguments to consistently be (ip,
        #       port, ...) across all the network readers/writers... but we
        #       want `interface` to be optional.  All kwargs need to come after
        #       all regular args, so we've assigned a default value of None to
        #       `port`.  But don't be confused, it is REQUIRED.
        #
        if not port:
            raise TypeError('must specify `port`')
        # make sure port gets stored as an int, even if passed in as a string
        self.port = int(port)

        # prep eol
        #
        # NOTE: We're going to be looking for `eol` inside of the byte array
        #       returned by recv(), so it has to be encoded to bytes here
        #       regardless of `encoding`.
        #
        # NOTE: We set unescape to True because `eol` might be provided w/
        #       escaped out characters
        #
        if eol:
            eol = self._encode_str(eol, unescape=True)
        self.eol = eol

        # Where we'll aggregate incomplete records if an eol char is specified
        self.record_buffer = b''

        self.reuseaddr = reuseaddr
        self.reuseport = reuseport

        # initialize this now, so our socket is ready to accept connections
        # once constructed
        self.s_listening = self._open_socket()

        # these get set when we successfully accept() an incoming connection in read()
        self.s_connected = None
        self.client_addr = None

    ############################
    def __del__(self):
        if self.s_connected:
            logging.debug('__del__: closing s_connected')
            self._close_socket(self.s_connected)

    ############################
    def _open_socket(self):
        # create TCP socket
        s = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)

        # set sockopts
        if self.reuseaddr:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        if self.reuseport:
            try:  # Raspbian doesn't recognize SO_REUSEPORT
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
            except AttributeError:
                logging.warning('Unable to set socket REUSEPORT; may be unsupported.')

        # bind to specificed interface
        s.bind((self.interface, self.port))

        # start listening
        s.listen()

        return s

    ############################
    def _close_socket(self, s):
        s.shutdown(socket.SHUT_RDWR)
        s.close()

    ############################
    def _get_connected_socket(self):
        # make sure we're already listening
        if not self.s_listening:
            self.s_listening = self._open_socket()
        if not self.s_listening:
            logging.error("failed to open socket")
            return

        # accept connections
        #
        # NOTE: This will block until we have an incoming connection.
        #
        s_connected, client_addr = self.s_listening.accept()
        logging.debug('got connection from %s', client_addr)
        return s_connected, client_addr

    ############################
    def _read_size(self, size):
        try:
            # NOTE: This will block until there is *something* to return, but
            #       it won't wait for the full `size` before returning.
            record = self.s_connected.recv(size)
            # catch disconnected socket
            #
            # NOTE: If remote side disconnects, recv() "successfully" returns 0
            #       bytes.  We have to turn that into a failure so we
            #       re-establish comms before trying to recv() again.
            #
            if len(record) == 0:
                raise OSError("socket disconneced")
        except OSError as e:
            logging.error('TCPReader recv error: %s', str(e))
            # nuke the socket so we reconnect on next read()
            self._close_socket(self.s_connected)
            self.s_connected = None
            return None
        logging.debug('TCPReader._read_size: received %d bytes', len(record))
        return record

    ############################
    def _read_to_eol(self):
        while self.eol not in self.record_buffer:
            try:
                record = self.s_connected.recv(READ_BUFFER_SIZE)
                # catch disconnected socket
                #
                # NOTE: If remote side disconnects, recv() "successfully"
                #       returns 0 bytes.  We have to turn that into a failure
                #       so we re-establish comms before trying to recv() again.
                #
                if len(record) == 0:
                    raise OSError("socket disconneced")
            except OSError as e:
                logging.error('TCPReader recv error: %s', str(e))
                # nuke the socket so we reconnect on next read()
                self._close_socket(self.s_connected)
                self.s_connected = None
                return None
            logging.debug('TCPReader._read_to_eol: received %d bytes', len(record))

            self.record_buffer += record

        # we've got `eol` in our buffer, split out the first record
        i = self.record_buffer.find(self.eol)
        # `i` is the index of the BEGINNING of our `eol` sequence
        record = self.record_buffer[:i]
        # beginning of NEXT message is at i+len(eol)
        self.record_buffer = self.record_buffer[i+len(self.eol):]
        return record

    ############################
    def read(self, size=None):
        """Read from TCP socket, either up to the next `eol` in the stream or up to
        `size` bytes (ignoring `eol` even if set!), return the result.
        """
        # If socket isn't ready, set it up.  If something fails, return w/out reading.
        if not self.s_connected:
            self.s_connected, self.client_addr = self._get_connected_socket()
        if not self.s_connected:
            logging.error('TCPReader.read: unable to get connected socket')
            return

        if size:
            record = self._read_size(size)
        elif self.eol:
            record = self._read_to_eol()
        else:
            # invalid, need `eol` or `size`
            logging.error('need either `eol` or `size`')
            return

        record = self._decode_bytes(record)
        return record
