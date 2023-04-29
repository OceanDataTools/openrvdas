#!/usr/bin/env python3

import logging
import sys

# Don't freak out if pyserial isn't installed - unless they actually
# try to instantiate a SerialWriter
try:
    import serial
    SERIAL_MODULE_FOUND = True
except ModuleNotFoundError:
    SERIAL_MODULE_FOUND = False

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.writer import Writer  # noqa: E402
from logger.utils.formats import Text     # noqa: E402


################################################################################
class SerialWriter(Writer):
    """
    Writes records to a serial port.
    """
    def __init__(self,  port, baudrate=9600, bytesize=8, parity='N',
                 stopbits=1, timeout=None, xonxoff=False, rtscts=False,
                 write_timeout=None, dsrdtr=False, inter_byte_timeout=None,
                 exclusive=None, eol='\n',
                 encoding='utf-8', encoding_errors='ignore', quiet=False):
        """
        By default, the SerialWriter write records to the specified serial port encoded by UTF-8
        and will ignore non unicode characters it encounters. These defaults may be changed by
        specifying.

        eol - if specified, append to end of records to signify end of line,
                otherwise use \n

        encoding - 'utf-8' by default. If empty or None, will throw type error.
                Other possible encodings are listed in online documentation here:
                https://docs.python.org/3/library/codecs.html#standard-encodings

        encoding_errors - 'ignore' by default. Other error strategies are 'strict',
                'replace', and 'backslashreplace', described here:
                https://docs.python.org/3/howto/unicode.html#encodings
        quiet - allows for the logger to silence warnings if not all the bits were succesfully
                written to the serial port.
        """
        super().__init__(input_format=Text)
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
        except serial.SerialException as e:
            raise serial.SerialException(f'Failed to open serial port {port}: {e}')

        self.eol = eol
        self.encoding = encoding
        self.encoding_errors = encoding_errors
        self.quiet = quiet

    ############################
    def write(self, record):
        if not record:
            return
        try:
            if self.eol:
                record += self.eol
            written = self.serial.write((record).encode(self.encoding))
            if not written and not self.quiet:
                logging.error("Not all bits written")
        except KeyboardInterrupt as e:
            raise e
        except TypeError as e:
            raise e
        except serial.serialutil.SerialException as e:
            logging.error(str(e))
