#!/usr/bin/env python3

import logging
import sys
from time import sleep
import os

try:
    from pymodbus.client import ModbusSerialClient
    from pymodbus.exceptions import ModbusIOException
    MODBUS_MODULE_FOUND = True
except ModuleNotFoundError:
    MODBUS_MODULE_FOUND = False

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa
from logger.utils.formats import Text  # noqa


###############################################################################
class ModBusSerialReader(Reader):
    """
    Read holding registers from a ModBus RTU serial device.
    """

    def __init__(self,
                 registers=None,
                 port="/dev/ttyUSB0",
                 baudrate=9600,
                 parity="N",
                 stopbits=1,
                 bytesize=8,
                 unit=1,
                 interval=10,
                 sep=" ",
                 encoding="utf-8",
                 encoding_errors="ignore",
                 timeout=None):

        super().__init__(output_format=Text,
                         encoding=encoding,
                         encoding_errors=encoding_errors)

        if not MODBUS_MODULE_FOUND:
            raise RuntimeError(
                "Modbus functionality not available. Install pymodbus: "
                '   pip install "pymodbus[serial]"'
            )

        # If registers is None, create a default 10-register block
        if registers is None:
            self.registers = [(0, 10)]
        # If registers is a string, parse as before
        elif isinstance(registers, str):
            self.registers = []
            for reg in registers.split(","):
                reg = reg.strip()
                if ":" in reg:
                    start, end = reg.split(":")
                    if start == "":
                        start = 0
                    if end == "":
                        raise ValueError(f'Invalid range "{reg}": open-ended upper bound not allowed.')
                    start = int(start)
                    end = int(end)
                    if end < start:
                        raise ValueError(f"Bad register range {reg}: end < start")
                    length = end - start + 1
                    self.registers.append((start, length))
                else:
                    self.registers.append((int(reg), 1))
        # If registers is already a list of tuples/blocks (for testing)
        elif isinstance(registers, list):
            self.registers = registers
        else:
            raise TypeError("registers must be None, a string, or a list of blocks")

        self.sep = sep
        self.unit = unit
        self.interval = interval

        # Create RTU client
        self.client = ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            parity=parity,
            stopbits=stopbits,
            bytesize=bytesize,
            timeout=timeout or 2,
            # framer='rtu'
        )

    ###############################################################################
    def read(self):
        """Read registers and return a text record."""
        if not self.client.connect():
            logging.error("ModBusSerialReader: unable to open serial port")
            # Return a record of "nan" for all registers
            return self.sep.join(["nan"] * sum(count for _, count in self.registers))

        results = []

        try:
            for start, count in self.registers:
                try:
                    response = self.client.read_holding_registers(
                        address=start,
                        count=count,
                        unit=self.unit
                    )

                    if response is None or getattr(response, 'isError', lambda: False)():
                        # simulate timeout: fill block with "nan"
                        results.extend(["nan"] * count)
                    else:
                        values = getattr(response, 'registers', [])
                        # If values missing, fill with "nan"
                        if not values:
                            results.extend(["nan"] * count)
                        else:
                            results.extend(str(v) for v in values)
                except Exception as err:
                    logging.error(f"ModBusSerialReader read error for registers {start}-{start+count-1}: {err}")
                    results.extend(["nan"] * count)

        finally:
            self.client.close()

        # Combine results and apply encoding
        record = self.sep.join(results)
        if isinstance(record, bytes):
            record = self._decode_bytes(record)

        # Wait for next poll
        sleep(self.interval)

        return record

