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

# On the send side of things, we can (and do) detect when a write has failed
# because the user's `record` was too big.  This is usually because the user is
# trying to send huge datagrams after looking up the "theoretical max size of a
# datagram" on wikipedia.  Well, it's called "theoretical" for a reason.  It's
# really the maximum size of the data portion of a UDP datagram, but that
# doesn't take into account extra header for IPv4/IPv6 or seemingly random
# system-level caps (e.g., Mac's socket implementation set maximum udp send
# size to 9K).
#
# When UDPWriter detects this condition, it fragments the record into smaller
# records and appends each fragment with this FRAGMENT_MARKER.  Inside
# UDPReader.read(), we check to see if a received datagram ends with this
# marker, and if it does, we read another datagram and combine the results
# (over and over until we get a datagram that doesn't end with the marker).
FRAGMENT_MARKER = b'\xff\xffTOOBIG\xff\xff'


################################################################################
class UDPReader(Reader):
    """Read UDP packets from network."""
    ############################
    def __init__(self, interface=None, port=None, mc_group=None,
                 reuseaddr=False, reuseport=False,
                 encoding='utf-8', encoding_errors='ignore'):
        """
        ```
        interface    IP (or resolvable name) of interface to listen on.  None or ''
                     will listen on INADDR_ANY (all interfaces).  If joining a
                     multicast group and None or '' specified, this will default
                     to whatever the system's hostname resolves to.  This IP should
                     not be on the loopback network (OK for testing, but won't work
                     in the real world).

        port         Port to listen to for packets.  REQUIRED

        mc_group     If specified, IP address of multicast group id to subscribe to.

        reuseaddr    Specifies wether we set SO_REUSEADDR on the created socket.  If
                     you don't know you need this, don't enable it.

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

        self.reuseaddr = reuseaddr
        self.reuseport = reuseport

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
        if self.reuseaddr:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        if self.reuseport:
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
            logging.error('UDPReader.read: unable to open UDP socket')
            return

        # Read datagrams until we get one that doesn't end with a FRAGMENT_MARKER
        record_buffer=b''
        while True:
            try:
                record = self.socket.recv(READ_BUFFER_SIZE)
            except OSError as e:
                logging.error('UDPReader error: %s', str(e))
                return None
            logging.debug('UDPReader.read: received %d bytes', len(record))

            if record.endswith(FRAGMENT_MARKER):
                # UDPWriter fragmented this record because it was too large to
                # send as a single datagram
                logging.info('UDPrader.read: detected fragmented packet')
                record_buffer += record.rsplit(FRAGMENT_MARKER, maxsplit=1)[0]
                logging.debug('record_buffer: %s', record_buffer)
            else:
                record_buffer += record
                break

        # we've got a whole record in our record_buffer, decode it
        return self._decode_bytes(record_buffer)
