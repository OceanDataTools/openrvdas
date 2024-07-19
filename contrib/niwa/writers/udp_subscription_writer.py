#!/usr/bin/env python3
import asyncio
import errno
import logging
import requests
import socket
import sys

from datetime import datetime, timedelta
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from django.conf import settings
from logger.writers.udp_writer import UDPWriter

# So that we can write the user's record no matter how silly big it is, we
# autodetect the system's maximum datagram size and write() fragments the
# record into smaller packets if needed.  Each fragmented packet is marked with
# FRAGMENT_MARKER so that UDPReader can notice and reassemble the record.
FRAGMENT_MARKER = b"\xff\xffTOOBIG\xff\xff"

# Maximum allowable size of a UDP datagram on this system, autodetect once at
# module load
#
# NOTE: You can test/debug the fragmentation code by loading the udp_writer
#       module and than manually setting udp_writer.MAXSIZE after autodetection
#       has happened.
#
MAXSIZE = None


def __detect_maxsize():
    """Autodetect the maximum datagram size we can send"""
    global MAXSIZE
    if MAXSIZE:
        return

    s = socket.socket(
        family=socket.AF_INET, type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP
    )

    # start with the maximum allowable size of a UDP packet, and work our way
    # down one byte at a time.
    #
    # FIXME: I know, I know.  Lame, slow, etc, a binary search would be "most
    #        correct", but I don't feel like making this go faster right now.
    #        And it's only done once, so whatever.
    #
    trysize = 65535
    while trysize > 0:
        logging.debug("__detect_maxsize: trying %d", trysize)
        try:
            s.sendto(b"a" * trysize, ("127.0.0.1", 9999))
        except OSError as e:
            if e.errno == errno.EMSGSIZE:
                trysize -= 1
                continue
            else:
                # For whatever reason, this won't work... print a warning
                logging.warning("__detect_maxsize: send() failed: %s", str(e))
                break
        break

    if not trysize:
        logging.warning(
            "Failed to autodetect maximum UDP datagram size.  Record fragmentation disabled"
        )
    else:
        logging.info("Detected maximum UDP datagram size %d", trysize)
        MAXSIZE = trysize


# attempt to detect maximum datagram size when module is loaded
__detect_maxsize()


################################################################################
class UDPSubscriptionWriter(UDPWriter):
    """Write UDP packets to subscribed IP addresses."""

    def __init__(
        self,
        subscription_logger_name,
        port=None,
        mc_interface=None,
        mc_ttl=3,
        num_retry=2,
        warning_limit=5,
        eol="",
        reuseaddr=False,
        reuseport=False,
        encoding="utf-8",
        encoding_errors="ignore",
    ):
        """Write records to a UDP network socket.
        ```
        destination  The destination to send UDP packets to. If '' or None,
                     the UDPWriter will broadcast to 255.255.255.255.  On a
                     system connected to more than one subnet, you'll want to
                     specify the broadcast address of the network you're trying
                     to send to (e.g., 192.168.1.255).

        port         Port to which packets should be sent.  REQUIRED

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

        reuseaddr    Specifies wether to set SO_REUSEADDR on the created socket.  If
                     you don't know you need this, don't enable it.

        reuseport    Specifies wether to set SO_REUSEPORT on the created socket.  If
                     you don't know you need this, don't enable it.

        encoding - 'utf-8' by default. If empty or None, do not attempt any
                decoding and return raw bytes. Other possible encodings are
                listed in online documentation here:
                https://docs.python.org/3/library/codecs.html#standard-encodings

        encoding_errors - 'ignore' by default. Other error strategies are
                'strict', 'replace', and 'backslashreplace', described here:
                https://docs.python.org/3/howto/unicode.html#encodings
        ```

        """
        super().__init__(
            port=port,
            mc_interface=mc_interface,
            mc_ttl=mc_ttl,
            num_retry=num_retry,
            warning_limit=warning_limit,
            eol=eol,
            reuseaddr=reuseaddr,
            reuseport=reuseport,
            encoding=encoding,
            encoding_errors=encoding_errors,
        )

        self.subscription_logger_name = subscription_logger_name
        self.subscribed_ip_addresses = []
        self.last_updated_subscriptions = datetime.now()

        self.sockets = {}

        self.api_headers = {"Authorization": settings.API_KEY}

        # TODO LW: implement these API endpoints and figure out the auth for them (api key?)

        try:
            id_response = requests.get(
                f"http://localhost/api/get_logger_id_by_name/{subscription_logger_name}",
                headers=self.api_headers,
            ).json()
            self.matching_logger_id = int(id_response.get("loggerId"))
            asyncio.run(self.get_ip_addresses())
        except Exception as e:
            logging.error(e)
            logging.error(
                f"Could not get matching logger id for logger named: {subscription_logger_name}"
            )

    async def get_ip_addresses(self):
        if self.matching_logger_id is not None:
            ip_response = requests.get(
                f"http://localhost/api/get_subscriptions_by_logger_id/{self.matching_logger_id}",
                headers=self.api_headers,
            ).json()
            self.subscribed_ip_addresses = ip_response.get("ipAddresses", [])
        else:
            self.subscribed_ip_addresses = []

        self.last_updated_subscriptions = datetime.now()

    def _open_socket(self, destination):
        """Do socket prep so we're ready to write().  Returns socket object or None on
        failure.
        """
        udp_socket = socket.socket(
            family=socket.AF_INET, type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP
        )
        if self.reuseaddr:
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        if self.reuseport:
            try:  # Raspbian doesn't recognize SO_REUSEPORT
                udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
            except AttributeError:
                logging.warning("Unable to set socket REUSEPORT; may be unsupported")

        try:
            udp_socket.connect((destination, self.port))
            return udp_socket
        except OSError as e:
            logging.error("Unable to connect to %s:%d - %s", destination, self.port, e)
            return None

    def write(self, record):
        # update subscribers but don't interupt the current message
        if self.last_updated_subscriptions < datetime.now() - timedelta(seconds=20):
            asyncio.run(self.get_ip_addresses())

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

        # Encode the record, so we're dealing with bytes from here on out
        record = self._encode_str(record)

        # Fragment record if needed, and recurse.
        if len(record) > MAXSIZE:
            record_list = []
            max_fragment_size = MAXSIZE - len(FRAGMENT_MARKER)
            fragment_sizes = []
            while len(record) > max_fragment_size:
                r = record[:max_fragment_size] + FRAGMENT_MARKER
                record_list.append(r)
                fragment_sizes.append(str(len(r)))
                record = record[max_fragment_size:]
            # last record doesn't get FRAGMENT_MARKER
            record_list.append(record)
            fragment_sizes.append("{} bytes".format(len(record)))
            fragment_sizes = ", ".join(fragment_sizes)
            logging.info(
                "write: fragmented record into %d datagrams: %s",
                len(record_list),
                fragment_sizes,
            )
            logging.debug(str(record_list))

            # change our encoding to binary temporarily, because we've already
            # encoded to binary and added our marker (which has non-utf chars
            # in it)
            old_encoding = self.encoding
            self.encoding = None
            self.write(record_list)
            # restore old encoding
            self.encoding = old_encoding
            return

        for ip_address in self.subscribed_ip_addresses:
            # If socket isn't connected, try reconnecting. If we can't
            # reconnect, complain and return without writing.
            if not self.sockets.get(ip_address):
                self.sockets[ip_address] = self._open_socket(ip_address)
            if not self.sockets.get(ip_address):
                logging.error("Unable to write record to %s:%d", ip_address, self.port)
                return

            num_tries = bytes_sent = 0
            rec_len = len(record)
            while num_tries <= self.num_retry and bytes_sent < rec_len:
                try:
                    bytes_sent = self.sockets.get(ip_address).send(record)

                    # If here, write succeeded. Reset warnings
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
                            logging.info(
                                "UDPWriter.write() succeeded in writing after series of "
                                "failures; resetting warnings."
                            )
                        self.num_warnings = 0  # we've succeeded

                except (OSError, ConnectionRefusedError) as e:
                    # If we failed, complain, unless we've already complained too much
                    self.good_writes = 0
                    if self.num_warnings < self.warning_limit:
                        logging.error(
                            "UDPWriter: send() error: %s: %s", self.target_str, str(e)
                        )
                        self.num_warnings += 1
                        if self.num_warnings == self.warning_limit:
                            logging.error("UDPWriter.write() - muting errors")
                num_tries += 1

            logging.debug(
                "UDPWriter.write() wrote %d/%d bytes after %d tries",
                bytes_sent,
                rec_len,
                num_tries,
            )