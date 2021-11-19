#!/usr/bin/env python3

import logging
import socket
import struct
import sys
from time import sleep

# Don't freak out if pyModbusTCP isn't installed - unless they actually
# try to instantiate a ModBusReader
try:
    from pyModbusTCP.client import ModbusClient
    MODBUS_MODULE_FOUND = True
except ModuleNotFoundError:
    MODBUS_MODULE_FOUND = False

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402
from logger.utils.formats import Text  # noqa: E402


################################################################################
class ModBusTCPReader(Reader):
    """
    Read registers from a ModBusTCP device.
    """
    ############################

    def __init__(self, registers, host='localhost', port=502,
                 interval=10,  sep=' ', encoding='utf-8',
                 encoding_errors='ignore'):
        """
        ```
        registers  A comma-separated list of integers and/or ranges. A range
                   is an int:int pair, where either or both of the ints may
                   be omitted to mean the extreme values (0 or sys.maxsize).
        ```
        Example:
        ```
          reader = ModBusReader('3,5:7,9,11')

          record = reader.read()
        ```
        should yield ``'<reg_3> <reg_5> <reg_6> <reg_7> <reg_9> <reg_11>'``.

        ```
        host       Host to listen to for packets

        port       Port to listen to for packets

        interval   Interval in seconds to poll for new data

        sep        How to seperate the register values in the output record

        encoding - 'utf-8' by default. If empty or None, do not attempt any decoding
                and return raw bytes. Other possible encodings are listed in online
                documentation here:
                https://docs.python.org/3/library/codecs.html#standard-encodings

        encoding_errors - 'ignore' by default. Other error strategies are 'strict',
                'replace', and 'backslashreplace', described here:
                https://docs.python.org/3/howto/unicode.html#encodings
        ```
        """

        super().__init__(output_format=Text,
                         encoding=encoding,
                         encoding_errors=encoding_errors)

        if not MODBUS_MODULE_FOUND:
            raise RuntimeError('Modbus functionality not available. Please '
                               'install Python module pyModbusTCP.')

        if registers.endswith(":"):
            raise ValueError('Registers value cannot end with an ambiguous '
                             'maximum register number (i.e. "5:").')

        self.registers = []
        try:
            for register in registers.split(','):
                logging.debug('ModBusReader parsing register "%s"', register)
                # If register spec is a range, num:num, store as tuple of ints
                if register.find(':') > -1:
                    (start, end) = register.split(':')
                    if start == '':  # if missing start, e.g.   ':5'
                        start = 0
                    if end == '':  # if missing end, e.g.   '1:'
                        raise ValueError('Register value range cannot end with '
                                         'an ambiguous maximum register number '
                                         '(i.e. "5:").')
                    self.registers.concat((int(start), int(end)-int(start)))

                # If register is a simple number
                else:
                    self.registers.append(int(register))

        except ValueError as e:
            logging.error('Bad register format "%s" - %s', register, e)
            raise e

        self.sep = sep
        self.interval = interval
        self.client = ModbusClient(host=host, port=port, auto_open=True, auto_close=True)

    ############################
    def read(self):
        """
        Read the specified registers. Return values as a text record. Wait the
        specified interval before reading again
        """

        try:
            readings = []
            for register in self.registers:
                if isinstance(register, tuple):
                    readings.append(self.client.read_holding_registers(register[0],register[1]))
                else:
                    readings.append(self.client.read_holding_registers(register,1))

            record = self.sep.join(regs)
        except OSError as e:
            logging.error('ModBusReader error: %s', str(e))
            return None
        logging.debug('ModBusReader.read() received %d bytes', len(record))
        return self._decode_bytes(record)

        sleep(self.interval)
