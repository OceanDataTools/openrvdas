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
    Read text records from a serial port.
    """

    def __init__(self,  port, baudrate=9600, bytesize=8, parity='N',
                 stopbits=1, timeout=None, xonxoff=False, rtscts=False,
                 write_timeout=None, dsrdtr=False, inter_byte_timeout=None,
                 exclusive=None, max_bytes=None, eol=None):
        """If max_bytes is specified on initialization, read up to that many
        bytes when read() is called. If eol is not specified, read() will
        read up to the first newline it receives. In both cases, if
        timeout is specified, it will return after timeout with as many
        bytes as it has succeeded in reading.

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
        super().__init__(output_format=Text)

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
            sys.exit(1)

        self.max_bytes = max_bytes

        # 'eol' comes in as a (probably escaped) string. We need to
        # unescape it, which means converting to bytes and back.
        if eol is not None:
            eol = eol.encode().decode("unicode_escape").encode('utf8')
        self.eol = eol

    ############################
    def read(self):
        try:
            if self.eol:
                record = self.serial.read_until(self.eol, self.max_bytes)
            elif self.max_bytes:
                record = self.serial.read(self.max_bytes)
            else:
                record = self.serial.readline()
            if not record:
                return None
            return record.decode('utf-8').rstrip()
        except serial.serialutil.SerialException as e:
            logging.error(str(e))
            return None
        except KeyboardInterrupt as e:
            raise e
