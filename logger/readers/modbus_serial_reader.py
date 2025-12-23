#!/usr/bin/env python3
"""
''
ModBusSerialReader
==================

This module provides a thread-safe reader for polling Modbus RTU devices
over a serial connection. It supports single-slave and multi-slave setups,
multiple Modbus function types, and flexible output formats (binary or text).

Key Features
------------
- Reads holding registers, input registers, coils, and discrete inputs.
- Supports configuration via direct register specification or YAML scan file.
- Partial failure tolerance: failed polls return placeholder values without
  stopping other reads.
- Exponential backoff for serial connection retries (1s → 30s max).
- Thread-safe access via internal Lock.
- Output can be raw bytes (binary) or encoded text with customizable separator.
- Automatic cleanup of the serial port on `stop()` or object deletion.

Typical Usage
-------------
    reader = ModBusSerialReader(
        registers="0:5,10:15",
        port="/dev/ttyUSB0",
        baudrate=19200,
        interval=5,
        encoding="utf-8"
    )
    data = reader.read()
    print(data)
    reader.stop()

Dependencies
------------
- pymodbus (optional; raises RuntimeError if missing)
- PyYAML
- Standard Python libraries: logging, time, threading, sys, os.path
'''
"""

import logging
import sys
import yaml
import time
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
    Read data from Modbus RTU devices over a serial connection.
    """

    ############################
    def __init__(self,
                 registers=None,
                 port="/dev/ttyUSB0",
                 baudrate=9600,
                 parity="N",
                 stopbits=1,
                 bytesize=8,
                 scan_file=None,
                 slave=1,
                 function='holding_registers',
                 interval=10,
                 sep=" ",
                 encoding="utf-8",
                 encoding_errors="ignore",
                 timeout=None):
        """
        ```
        registers - Comma-separated string (e.g. '0:5,10:15') or list of
                    tuples [(start,count), ...] specifying which registers
                    to poll. Required if scan_file is not provided.

        port - Serial port device (e.g. '/dev/ttyUSB0').

        baudrate - Serial connection baud rate (default 9600).

        parity - Serial parity, one of 'N', 'E', 'O' (default 'N').

        stopbits - Number of stop bits (default 1).

        bytesize - Number of data bits (default 8).

        scan_file - Optional YAML file specifying multiple slaves, functions,
                    and register blocks. Overrides registers/slave/function
                    parameters if provided.

        slave - Modbus slave ID (default 1). Ignored if scan_file is provided.

        function - Modbus function type to read: 'holding_registers',
                   'input_registers', 'coils', or 'discrete_inputs'.
                   Ignored if scan_file is provided.

        interval - Seconds between consecutive reads. Must be >= 0.

        sep - Separator string used when encoding output as text. Ignored
              if encoding is None.

        encoding - Character encoding for text output (default 'utf-8').
                   If None, raw bytes are returned.

        encoding_errors - Strategy for handling encoding errors ('ignore'
                          by default). Other options: 'strict', 'replace',
                          'backslashreplace'.

        timeout - Max time in seconds to wait for serial response. Defaults
                  to 2 seconds if None.
        ```
        """

        super().__init__(output_format=Text,
                         encoding=encoding,
                         encoding_errors=encoding_errors)

        if not MODBUS_MODULE_FOUND:
            raise RuntimeError(
                "Modbus functionality not available. Install pymodbus: "
                'pip install "pymodbus[serial]"'
            )

        self._FUNCTION_MAP = {
            "holding_registers": "read_holding_registers",
            "input_registers": "read_input_registers",
            "coils": "read_coils",
            "discrete_inputs": "read_discrete_inputs",
        }

        self.polls = []
        if scan_file:
            self._load_scan_file(scan_file)
        else:
            if registers is None:
                raise ValueError("registers required when scan_file not provided")
            self.polls = [{
                "slave": slave,
                "function": function,
                "registers": self._parse_registers(registers)
            }]

        self.sep = sep if encoding is not None else None
        self.interval = interval
        self._next_read_time = 0.0
        self._connected = False
        self._reconnect_delay = 1.0
        self._reconnect_delay_max = 30.0
        self._next_connect_time = 0.0
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
    def _reset_client(self):
        """Hard-reset of the serial client."""
        try:
            self.client.close()
        except Exception:
            pass

        self._connected = False

        now = time.monotonic()
        self._next_connect_time = now + self._reconnect_delay
        self._reconnect_delay = min(
            self._reconnect_delay * 2,
            self._reconnect_delay_max
        )
        logging.info(
            "Next Modbus reconnect attempt in %.1f seconds",
            self._reconnect_delay
        )

    ############################
    def _parse_register_spec(self, spec):
        """Parse a single register spec into (start, count)."""
        if ":" in spec:
            start, end = spec.split(":", 1)
            if end == "":
                raise ValueError(f"Ambiguous register range: '{spec}'")
            start = int(start) if start else 0
            end = int(end)
            if start < 0 or end < start:
                raise ValueError(f"Invalid register range: '{spec}'")
            return (start, end - start + 1)
        addr = int(spec)
        if addr < 0:
            raise ValueError(f"Invalid register address: '{spec}'")
        return (addr, 1)

    ############################
    def _validate_blocks(self, blocks):
        """Validate and individual register block"""
        validated = []
        for block in blocks:
            if not (
                isinstance(block, tuple)
                and len(block) == 2
                and all(isinstance(x, int) and x >= 0 for x in block)
            ):
                raise ValueError(f"Invalid register block: {block}")
            validated.append(block)
        return validated

    ############################
    def _parse_registers(self, registers):
        """Parse comma-separated string or list into [(start, count), ...] blocks."""
        if registers is None:
            return [(0, 10)]
        if isinstance(registers, list):
            return self._validate_blocks(registers)
        if not isinstance(registers, str):
            raise TypeError("registers must be str, list, or None")

        blocks = []
        for spec in registers.split(","):
            spec = spec.strip()
            if spec:
                blocks.append(self._parse_register_spec(spec))
        if not blocks:
            raise ValueError("No valid registers specified")
        return blocks

    ############################
    def _client_connected(self) -> bool:
        """Connect if not already connected. Returns True if OK."""
        if self._connected:
            return True

        now = time.monotonic()
        if now < self._next_connect_time:
            return False

        try:
            self._connected = self.client.connect()
        except ModbusException as exc:
            logging.error(f"ModbusException: connect() failed: {exc}")
            self._reset_client()
            return False
        except Exception as exc:
            logging.error(f"Exception: connect() failed: {exc}")
            self._reset_client()
            return False

        if not self._connected:
            logging.error("ModBusSerialReader: unable to open serial port")
            self._reset_client()
            return False

        self._reconnect_delay = 1.0
        self._next_connect_time = 0.0

        return self._connected

    ############################
    def _load_scan_file(self, path):
        """Load the YAML-formatted scan file"""
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)

        if "polls" not in cfg:
            raise ValueError("scan_file must contain 'polls' list")

        for poll in cfg["polls"]:
            slave = poll["slave"]
            function = poll.get("function", "holding_registers")
            registers = poll["registers"]

            self.polls.append({
                "slave": slave,
                "function": function,
                "registers": self._parse_registers(registers)
            })

    ############################
    def _format_record(self, readings: list[list[int | bool | None]], function: str) -> bytes | str:
        """
        Flatten nested register/coil values into a single record.

        Parameters
        ----------
        readings : list[list[int | bool | None]]
            Nested lists of values returned from Modbus reads.

        function : str
            Modbus function type. Determines formatting behavior.
            Expected values:
              - "holding_registers"
              - "input_registers"
              - "coils"
              - "discrete_inputs"

        Behavior
        --------
        - encoding is None:
            - Registers → 16-bit unsigned big-endian
            - Coils/discrete_inputs → packed bits (LSB-first)
            - None values → 0
        - Otherwise convert to text and encode with _encode_str, using self.sep
        """

        flat_values: list[int | bool | None] = []
        for block in readings:
            if block:
                flat_values.extend(block)

        is_coils = function in ("coils", "discrete_inputs")

        # ------------------------------------------------------------------
        # Binary
        # ------------------------------------------------------------------
        if self.encoding is None:
            if not flat_values:
                return b""

            if is_coils:
                # Pack bits LSB-first, per Modbus spec
                byte_vals = []
                current_byte = 0
                bit_index = 0

                for bit in flat_values:
                    bit_val = 1 if bit else 0
                    current_byte |= bit_val << bit_index
                    bit_index += 1

                    if bit_index == 8:
                        byte_vals.append(current_byte)
                        current_byte = 0
                        bit_index = 0

                if bit_index:
                    byte_vals.append(current_byte)

                return bytes(byte_vals)

            # Registers: 16-bit unsigned big-endian
            return b"".join(
                int(val or 0).to_bytes(2, byteorder="big", signed=False)
                for val in flat_values
            )

        # ------------------------------------------------------------------
        # Encoded text
        # ------------------------------------------------------------------
        text_values = [
            str(val) if val is not None else "nan"
            for val in flat_values
        ]
        return self._encode_str(self.sep.join(text_values))


    ############################
    def read(self):
        """Read all configured polls and return a list of formatted records per slave.

        Returns:
            list[bytes|str|None]: None for polls that cannot be read; otherwise formatted output.
        """
        with self._lock:
            now = time.monotonic()
            if now < self._next_read_time:
                time.sleep(self._next_read_time - now)
            start_time = time.monotonic()

            if not self._client_connected():
                return None

            records = []

            for poll in self.polls:
                slave = poll["slave"]
                func_name = self._FUNCTION_MAP.get(poll["function"])

                if not func_name:
                    logging.warning("Invalid function for slave=%s: %s", slave, poll["function"])
                    total_count = sum(count for _, count in poll["registers"])
                    readings = [[None] * total_count]
                else:
                    func = getattr(self.client, func_name)
                    readings = []
                    for start, count in poll["registers"]:
                        try:
                            resp = func(address=start, count=count, unit=slave)
                            if resp is None or getattr(resp, "isError", lambda: False)():
                                logging.warning("Failed to read slave=%d addr=%d:%d", slave, start, count)
                                readings.append([None] * count)
                            else:
                                values = getattr(resp, "registers", getattr(resp, "bits", None))
                                readings.append(values or [None] * count)
                        except (ModbusException, OSError, ConnectionError, ValueError, AttributeError) as exc:
                            logging.warning("Modbus read error slave=%d addr=%d:%d: %s", slave, start, count, exc)
                            readings.append([None] * count)
                            self._reset_client()
                            break

                record = self._format_record(readings, poll["function"])
                if self.encoding is not None and isinstance(record, bytes):
                    record = record.decode(self.encoding, errors=self.encoding_errors)
                    record = self._encode_str(f"slave {slave}:{self.sep}{record}")
                records.append(record)

            self._next_read_time = start_time + self.interval
            return records

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
