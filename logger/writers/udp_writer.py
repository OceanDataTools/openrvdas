#!/usr/bin/env python3

import json
import logging
import socket
import struct
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.writers.writer import Writer


class UDPWriter(Writer):
    """Write UDP packets to network."""

    def __init__(self, port, destination='',
                 interface='',  # DEPRECATED!
                 mc_interface=None, mc_ttl=3, num_retry=2, warning_limit=5, eol='',
                 encoding='utf-8', encoding_errors='ignore'):
        """Write records to a UDP network socket.
        ```
        port         Port to which packets should be sent

        destination  The destination to send UDP packets to. If omitted (or None)
                     is equivalent to specifying destination='<broadcast>',
                     which will send to all available interfaces.

                     Setting destination='255.255.255.255' means broadcast
                     to local network. To broadcast to a specific interface,
                     set destination to the broadcast address for that network.

        interface    DEPRECATED - If specified, the network interface to
                     send from. Preferred usage is to use the 'destination'
                     argument and specify the broadcast address of the desired
                     network.

        mc_interface REQUIRED for multicast, the interface to send from.  Can be
                     specified as either IP or a resolvable hostname.

        mc_ttl       For multicast, how many network hops to allow.

        num_retry    Number of times to retry if write fails. If writer exceeds
                     this number, it will give up on writing the message and
                     move on.

        warning_limit  Number of times the writer gives up on writing a message
                     (without any intervening successes) before it gives up complaining
                     about failures.

        eol          If specified, an end of line string to append to record
                     before sending.

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
        self.good_writes = 0 # consecutive good writes, for detecting UDP errors

        # 'eol' comes in as a (probably escaped) string. We need to
        # unescape it, which means converting to bytes and back.
        if eol is not None and self.encoding:
            eol = self._unescape_str(eol)
        self.eol = eol

        self.target_str = 'interface: %s, destination: %s, port: %d' % (
            interface, destination, port)

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
        if destination:
            destination = socket.gethostbyname(destination)
        if interface:
            logging.warning('DEPRECATED: UDPWriter(interface=%s). Instead of the '
                            '"interface" parameter, UDPWriters should use the'
                            '"destination" parameter. To broadcast over a specific '
                            'interface, specify UDPWriter(destination=<interface '
                            'broadcast address>) address as the destination.',
                            interface)
            interface = socket.gethostbyname(interface)

        if interface and destination:
            # At the moment, we don't know how to do both interface and
            # multicast/unicast. If they've specified both, then complain
            # and ignore the interface part.
            logging.warning('UDPWriter doesn\'t yet support specifying both '
                            'interface and destination. Ignoring interface '
                            'specification.')

        # THE FOLLOWING USE OF interface PARAMETER IS PARTIALLY BROKEN: it
        # will fail if the netmask is not 255.255.255.0. This is why we
        # deprecate the interface param.
        #
        # If they've specified the interface we're supposed to be sending
        # via, then we have to do a little legerdemain: we're going to
        # connect to the broadcast address of the specified interface as
        # our destination. The broadcast address is just the normal
        # address with the last tuple replaced by ".255".
        elif interface:
            if interface == '0.0.0.0':  # local network
                destination = '255.255.255.255'
            elif interface in ['<broadcast>', 'None']:
                destination = '<broadcast>'
            else:
                # Change interface's lowest tuple to 'broadcast' value (255)
                destination = interface[:interface.rfind('.')] + '.255'

        # If no destination, it's a broadcast; set flag allowing broadcast and
        # set dest to special string
        elif not destination:
            destination = '<broadcast>'

        self.destination = destination
        # make sure port gets stored as an int, even if passed in as a string
        self.port = int(port)

        # multicast options
        if mc_interface:
            # resolve once in constructor
            mc_interface = socket.gethostbyname(mc_interface)
        self.mc_interface = mc_interface
        self.mc_ttl = mc_ttl

        # socket get's initialized on-demand in write()
        self.socket = None

    ############################
    def _open_socket(self):
        """Try to open and return the network socket.
        """
        udp_socket = socket.socket(family=socket.AF_INET,
                                   type=socket.SOCK_DGRAM,
                                   proto=socket.IPPROTO_UDP)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        try:  # Raspbian doesn't recognize SO_REUSEPORT
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
        except AttributeError:
            logging.warning('Unable to set socket REUSEPORT; may be unsupported')

        # set multicast/broadcast options
        if self.mc_interface:
            # set the time-to-live for messages
            udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL,
                                  struct.pack('b', self.mc_ttl))
            # set outgoing multicast interface
            udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                  socket.inet_aton(self.mc_interface))
        else:
            # maybe broadcast, but very non-trivial to detect broadcast IP, so
            # we set the broadcast flag anytime we're not doing multicast
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)

        try:
            udp_socket.connect((self.destination, self.port))
            return udp_socket
        except OSError as e:
            logging.error('Unable to connect to %s:%d - %s', self.destination, self.port, e)
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

                # If here, write at least partially succeeded. Reset warnings
                #
                # NOTE: If the host is unreachable, every other send will fail.
                #       Since UDP doesn't actually know it failed, the initial
                #       send() cannot fail.  However, the network stack will
                #       see the ICMP host unreachable message and will store
                #       THAT as the the error message for next write, then the
                #       next send fails and clears the error...  Then the next
                #       "succeeds" and the next fails, etc, etc
                #
                #       So we look for 2 consecutive "successful" writes before
                #       resetting num_warnings.
                #
                self.good_writes += 1
                if self.good_writes >= 2:
                    if self.num_warnings == self.warning_limit:
                        logging.info('UDPWriter.write() succeeded in writing after series of '
                                     'failures; resetting warnings.')
                    self.num_warnings = 0  # we've succeeded

            except (OSError, ConnectionRefusedError) as e:
                # If we failed, complain, unless we've already complained too much
                self.good_writes = 0
                if self.num_warnings < self.warning_limit:
                    logging.error('UDPWriter: send() error: %s: %s', self.target_str, str(e))
                    self.num_warnings += 1
                    if self.num_warnings == self.warning_limit:
                        logging.error('UDPWriter.write() - muting errors')
            num_tries += 1

        logging.debug('UDPWriter.write() wrote %d/%d bytes after %d tries',
                      bytes_sent, rec_len, num_tries)
