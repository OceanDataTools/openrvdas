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
    def __init__(self, interface, port,
                 mc_group=None, eol=None,
                 encoding='utf-8', encoding_errors='ignore'):
        """
        ```
        interface    IP (or resolvable name) of interface to listen on.  None or ''
                     will listen on INADDR_ANY (all interfaces).  If joining a
                     multicast group and None or '' specified, this will default
                     to whatever the system's hostname resolves to.  This IP should
                     not be on the loopback network (OK for testing, but won't work
                     in the real world).

        port         Port to listen to for packets

        mc_group     If specified, IP address of multicast group id to subscribe to.

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

        if interface:
            # resolve once in constructor
            interface = socket.gethostbyname(interface)
        self.interface = interface

        # prep multicast parameters
        if mc_group:
            # resolve once in constructor
            mc_group = socket.gethostbyname(mc_group)
            if not interface:
                # multicast needs to specify interface to use, so let's pick a
                # sane default
                #
                # NOTE: This means hostname cannot be an alias to localhost, or
                #       you won't be able to send IGMP packets correctly.
                #
                self.interface = socket.gethostbyname(socket.gethostname())

        self.mc_group = mc_group

        # make sure port gets stored as an int, even if passed in as a string
        self.port = int(port)

        # Where we'll aggregate incomplete records if an eol char is specified
        self.record_buffer = ''

        # socket gets initialized on-demand in read()
        self.socket = None

    ############################
    def _open_socket(self):
        """Do socket prep so we're ready to read().  Returns socket object or None on
        failure.
        """
        sock = socket.socket(family=socket.AF_INET,
                             type=socket.SOCK_DGRAM,
                             proto=socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        try:  # Raspbian doesn't recognize SO_REUSEPORT
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
        except AttributeError:
            logging.warning('Unable to set socket REUSEPORT; may be unsupported.')

        # If mc_group is specified, subscribe to it as a multicast group
        if self.mc_group:
            # set outgoing multicast interface
            #
            # NOTE: Can't use loopback device for this, otherwise IGMP packets
            #       never leave the system, and you never actually join the
            #       group.
            #
            if self.interface.startswith('127.'):
                logging.warning("Can't use loopback device for joining multicast groups.  Make "
                                "sure your system's hostname does NOT resolve to something in "
                                "the 127.0.0.0/8 address block (e.g., localhost, 127.0.0.1), or "
                                "specify the interface to use by passing its IP address as the "
                                "`interface` parameter.  (You can ignore this message if you're "
                                "actually just doing loopback testing.)")
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                  socket.inet_aton(self.interface))

            # join the group via IGMP
            #
            # NOTE: Since these are both already encoded as binary by
            #       inet_aton(), we can just concatenate them.  Alternatively,
            #       could use struct.pack("4s4s", ...) to create a struct to
            #       pass into setsockopt()
            #
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                            socket.inet_aton(self.mc_group) + socket.inet_aton(self.interface))

            # bind to mc_group:port
            sock.bind((self.mc_group, self.port))

        else:
            # broadcast or unicast, bind to specificed interface
            sock.bind((self.interface, self.port))

        return sock

    ############################
    def read(self):
        """
        Read the next UDP packet.
        """
        # If socket isn't ready, set it up.  If something fails, return w/out reading.
        if not self.socket:
            self.socket = self._open_socket()
        if not self.socket:
            logging.error('Unable to read record')
            return

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
