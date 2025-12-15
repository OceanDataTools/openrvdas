#!/usr/bin/env python3

import logging
import sys
from threading import Lock

try:
    from pymodbus.client import ModbusSerialClient
    from pymodbus import ModbusException
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
    Keeps the port open between reads and auto-reconnects if needed.
    """

    def __init__(self,
                 registers=None,
                 port="/dev/ttyUSB0",
                 baudrate=9600,
                 parity="N",
                 stopbits=1,
                 bytesize=8,
                 slave=1,
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
                'pip install "pymodbus[serial]"'
            )

        if registers is None:
            self.registers = [(0, 10)]

        elif isinstance(registers, str):
            self.registers = []
            for reg in registers.split(","):
                reg = reg.strip()

                if ":" in reg:
                    start, end = reg.split(":")
                    start = int(start) if start else 0
                    if end == "":
                        raise ValueError(f"Invalid range '{reg}': missing upper bound")

                    end = int(end)
                    if end < start:
                        raise ValueError(f"Bad register range {reg}: end < start")

                    self.registers.append((start, end - start + 1))

                else:
                    self.registers.append((int(reg), 1))

        elif isinstance(registers, list):
            self.registers = registers

        else:
            raise TypeError("registers must be None, a string, or a list")

        self.sep = sep
        self.slave = slave
        self.interval = interval
        self._connected = False

        # Thread-safe access
        self._lock = Lock()

        self.client = ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            parity=parity,
            stopbits=stopbits,
            bytesize=bytesize,
            timeout=timeout or 2,
        )

    ############################
    def _client_connected(self):
        """Connect if not already connected. Returns True if OK."""
        if self._connected:
            return True

        try:
            self._connected = self.client.connect()
        except ModbusException as exc:
            logging.error(f"ModbusException: connect() failed: {exc}")
            self._connected = False
        except Exception as exc:
            logging.error(f"Exception: connect() failed: {exc}")
            self._connected = False

        if not self._connected:
            logging.error("ModBusSerialReader: unable to open serial port")

        return self._connected

    ############################
    def read(self):
        """Read registers and return a text record."""

        total_regs = sum(count for _, count in self.registers)
        nan_record = self.sep.join(["nan"] * total_regs)

        with self._lock:
            if not self._client_connected():
                return nan_record

            results = []

            for start, count in self.registers:
                try:
                    resp = self.client.read_holding_registers(
                        address=start,
                        count=count,
                        slave=self.slave
                    )

                    if resp is None or getattr(resp, "isError", lambda: True)():
                        results.extend(["nan"] * count)
                        continue

                    values = getattr(resp, "registers", None)
                    if not values:
                        results.extend(["nan"] * count)
                    else:
                        results.extend(str(v) for v in values)

                except ModbusException as exc:
                    logging.error(
                        f"ModbusException: error reading registers {start}-{start+count-1}: {exc}"
                    )
                    results.extend(["nan"] * count)
                    self.stop()
                except Exception as exc:
                    logging.error(
                        f"Exception: error reading registers {start}-{start+count-1}: {exc}"
                    )
                    results.extend(["nan"] * count)
                    self.stop()

            record = self.sep.join(results)

            if isinstance(record, bytes):
                record = self._decode_bytes(record)

            return record

    ############################
    def stop(self):
        """Explicitly close the serial port."""
        with self._lock:
            try:
                self.client.close()
            except Exception:
                pass
            self._connected = False

    ############################
    def __del__(self):
        """Destructor — ensures port is closed safely."""
        try:
            self.stop()
        except Exception:
            pass
