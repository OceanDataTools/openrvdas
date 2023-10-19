#!/usr/bin/env python3

import logging
import sys

# Don't freak out if pyserial isn't installed - unless they actually
# try to instantiate a SerialReader
try:
    import serial
    SERIAL_MODULE_FOUND = True
except ModuleNotFoundError:
    SERIAL_MODULE_FOUND = False

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402
from logger.utils.formats import Text  # noqa: E402


################################################################################
class SerialReader(Reader):
    """
    Read records from a serial port.
    """

    def __init__(self,  port, baudrate=9600, bytesize=8, parity='N',
                 stopbits=1, timeout=None, xonxoff=False, rtscts=False,
                 write_timeout=None, dsrdtr=False, inter_byte_timeout=None,
                 exclusive=None, max_bytes=None, eol=None,
                 encoding='utf-8', encoding_errors='ignore'):
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
        super().__init__(encoding=encoding,
                         encoding_errors=encoding_errors)

        if not SERIAL_MODULE_FOUND:
            raise RuntimeError('Serial port functionality not available. Please '
                               'install Python module pyserial.')
        try:
            self.serial = serial.Serial(port=port, baudrate=baudrate,
                                        bytesize=bytesize, parity=parity,
                                        stopbits=stopbits, timeout=timeout,
                                        xonxoff=xonxoff, rtscts=rtscts,
                                        write_timeout=write_timeout, dsrdtr=dsrdtr,
                                        inter_byte_timeout=inter_byte_timeout,
                                        exclusive=exclusive)
        except (serial.SerialException, serial.serialutil.SerialException) as e:
            logging.fatal('Failed to open serial port %s: %s', port, e)
            raise

        self.max_bytes = max_bytes
        self.encoding = encoding
        self.encoding_errors = encoding_errors

        # 'eol' comes in as a (probably escaped) string. We need to
        # unescape it, which means converting to bytes and back.
        #
        # NOTE: This block is different from SerialWriter because we use
        #       readline() in here, which already looks for trailing '\n' and
        #       handles encoding itself.
        #
        if eol is not None and self.encoding:
            eol = self._encode_str(eol, unescape=True)
        self.eol = eol

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

            if not record:
                return None
            return self._decode_bytes(record)

        except KeyboardInterrupt as e:
            raise e
        except serial.serialutil.SerialException as e:
            logging.error(str(e))
            return None
