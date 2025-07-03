#!/usr/bin/env python3

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(dirname(dirname(realpath(__file__)))))))
from logger.utils import timestamp  # noqa: E402
from logger.readers.serial_reader import SerialReader as Reader # noqa: E402

LOGGING_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'  # ISO 8601
TIMEZONE = timestamp.timezone.utc

################################################################################
class SerialReader(Reader):
    """
    Read records from a serial port.
    """

    def __init__(self,  port, baudrate=9600, bytesize=8, parity='N',
                 stopbits=1, timeout=None, xonxoff=False, rtscts=False,
                 write_timeout=None, dsrdtr=False, inter_byte_timeout=None,
                 exclusive=None, max_bytes=None, eol=None,
                 encoding='utf-8', encoding_errors='ignore',
                 prefix=None, sensor=None, time_format=LOGGING_TIME_FORMAT,
                 time_zone = TIMEZONE):
        """If max_bytes is specified on initialization, read up to that many
        bytes when read() is called. If eol is not specified, read() will
        read up to the first newline it receives. In both cases, if
        timeout is specified, it will return after timeout with as many
        bytes as it has succeeded in reading.

        By default, the SerialReader will read until it encounters a newline character.
        This behavior may be overwritten by specifying

        max_bytes - if specified, and write_timeout is None, read this many bytes per record.
                If write_timeout is not None, it may return fewer bytes.

        eol - if specified, read up until encountering the specified eol

        By default, the SerialReader will assume that records are encoded in UTF-8, and will
        ignore non unicode characters it encounters. These defaults may be changed by specifying

        encoding - 'utf-8' by default. If empty or None, do not attempt any decoding
                and return raw bytes. Other possible encodings are listed in online
                documentation here:
                https://docs.python.org/3/library/codecs.html#standard-encodings

        encoding_errors - 'ignore' by default. Other error strategies are 'strict',
                'replace', and 'backslashreplace', described here:
                https://docs.python.org/3/howto/unicode.html#encodings

        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ FOR WHOI ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        prefix - Add a prefix to all incoming messages, even if blank

        time_format - Format of time string added after prefix, Added ONLY if
                      there is prefix.

        sensor - Add string after timestamp, only if there is a prefix

        time_zone - Time zone used when adding the time string 
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ FOR WHOI ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        command line example:
        ```
          # Read serial port ttyr05 expecting a LF as end of record
          logger/listener/listen.py  --serial port=/dev/ttyr05,eol='\r'
        ```
        config example:
        ```
          class: SerialReader
          kwargs:
            baudrate: 4800
            port: /dev/ttyr05
            eol: \r
        ```
        """
        super().__init__(port=port, baudrate=baudrate,
                         bytesize=bytesize, parity=parity,
                         stopbits=stopbits, timeout=timeout,
                         xonxoff=xonxoff, rtscts=rtscts,
                         write_timeout=write_timeout, dsrdtr=dsrdtr,
                         inter_byte_timeout=inter_byte_timeout,
                         exclusive=exclusive, encoding=encoding,
                         encoding_errors=encoding_errors,
                         max_bytes=max_bytes, eol=eol)

        self.prefix = (
            self._encode_str(prefix, unescape=True)
            if prefix is not None and self.encoding
            else None
        )

        self.sensor = (
            self._encode_str(sensor + ' ', unescape=True)
            if sensor is not None and prefix is not None and self.encoding
            else b''
        )

        self.time_format = time_format
        self.time_zone = time_zone


    ############################
    def read(self):

        try:
            if self.eol:
                record = self.serial.read_until(expected=self.eol, size=self.max_bytes)
                # read_until()'s record includes a trailing 'eol', strip it off
                #
                # NOTE: But don't use rstrip which just looks explicitly for
                #       whitespace
                #
                record = record.rsplit(self.eol)[0]
            elif self.max_bytes:
                # no stripping on this one, just use exactly what we got
                record = self.serial.read(size=self.max_bytes)
            else:
                # readline()'s record includes the trailing '\n', strip it off
                record = self.serial.readline().rstrip()

            # if not record:
            #     return None

            if self.prefix:

                ts = timestamp.time_str(time_format=self.time_format,
                                        time_zone=self.time_zone)
                ts = self._encode_str(ts, unescape=True)

                record = self.prefix + b' ' + ts + b' ' + self.sensor + record

            else:
                record = record

            return self._decode_bytes(record)

        except KeyboardInterrupt as e:
            raise e
        except serial.serialutil.SerialException as e:
            logging.error(str(e))
            return None
