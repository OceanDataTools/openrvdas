#!/usr/bin/env python3

import json
import ipaddress
import logging
import socket
import struct
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord  # noqa: E402
from logger.writers.network_writer import NetworkWriter  # noqa: E402


class UDPWriter(NetworkWriter):
    """Write UDP packets to network."""

    def __init__(self, port, destination='',
                 interface='',  # DEPRECATED!
                 ttl=3, num_retry=2, eol=''):
        """
        Write text records to a network socket.
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

        ttl          For multicast, how many network hops to allow

        num_retry    Number of times to retry if write fails.

        eol          If specified, an end of line string to append to record
                     before sending.
        ```
        """
        self.ttl = ttl
        self.num_retry = num_retry
        self.eol = eol

        self.target_str = 'interface: %s, destination: %s, port: %d' % (
            interface, destination, port)

        if interface:
            logging.warning('DEPRECATED: UDPWriter(interface=%s). Instead of the '
                            '"interface" parameter, UDPWriters should use the'
                            '"destination" parameter. To broadcast over a specific '
                            'interface, specify UDPWriter(destination=<interface '
                            'broadcast address>) address as the destination.',
                            interface)

        if interface and destination:
            ipaddress.ip_address(interface)  # throw a ValueError if bad addr
            ipaddress.ip_address(destination)
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
                ipaddress.ip_address(interface)
                destination = interface[:interface.rfind('.')] + '.255'

        # If we've been given a destination, make sure it's a valid IP
        elif destination:
            ipaddress.ip_address(destination)

        # If no destination, it's a broadcast; set flag allowing broadcast and
        # set dest to special string
        else:
            destination = '<broadcast>'

        self.destination = destination
        self.port = port

        # Try opening the socket
        self.socket = self._open_socket()

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

        # Set the time-to-live for messages, in case of multicast
        udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL,
                              struct.pack('b', self.ttl))
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)

        try:
            udp_socket.connect((self.destination, self.port))
            return udp_socket
        except OSError as e:
            logging.warning('Unable to connect to %s:%d - %s', self.destination, self.port, e)
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
            except ConnectionRefusedError as e:
                logging.error('ERROR: %s: %s', self.target_str, str(e))
            num_tries += 1

        logging.debug('UDPWriter.write() wrote %d/%d bytes after %d tries',
                      bytes_sent, rec_len, num_tries)
