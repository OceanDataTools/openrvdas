#!/usr/bin/env python3

import logging
import sys
from time import sleep
import os

try:
    from pymodbus.client import ModbusSerialClient
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

        if registers is None:
            # Default: 10-register block starting at 0
            self.registers = [(0, 10)]

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
                    start = int(reg)
                    self.registers.append((start, 1))

        elif isinstance(registers, list):
            # Already parsed (used by unit tests)
            self.registers = registers

        else:
            raise TypeError("registers must be None, a string, or a list of blocks")

        self.sep = sep
        self.unit = unit
        self.interval = interval

        self.client = ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            parity=parity,
            stopbits=stopbits,
            bytesize=bytesize,
            timeout=timeout or 2,
        )

    ###############################################################################
    def read(self):
        """Read registers and return a text record."""

        total_regs = sum(count for _, count in self.registers)
        if not self.client.connect():
            logging.error("ModBusSerialReader: unable to open serial port")
            return self.sep.join(["nan"] * total_regs)

        results = []

        try:
            for start, count in self.registers:
                try:
                    response = self.client.read_holding_registers(
                        address=start,
                        count=count,
                        unit=self.unit
                    )

                    if response is None or getattr(response, "isError", lambda: False)():
                        results.extend(["nan"] * count)
                        continue

                    values = getattr(response, "registers", None)

                    if not values:
                        results.extend(["nan"] * count)
                    else:
                        results.extend(str(v) for v in values)

                except Exception as err:
                    logging.error(
                        f"ModBusSerialReader read error for registers {start}-{start + count - 1}: {err}"
                    )
                    results.extend(["nan"] * count)

        finally:
            self.client.close()

        record = self.sep.join(results)
        if isinstance(record, bytes):
            record = self._decode_bytes(record)

        sleep(self.interval)

        return record
