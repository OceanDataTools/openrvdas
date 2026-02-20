#!/usr/bin/env python3

import logging
import sys
import time
import yaml
from threading import Lock

# Optional dependency
try:
    from pyModbusTCP.client import ModbusClient
    MODBUS_MODULE_FOUND = True
except ModuleNotFoundError:
    MODBUS_MODULE_FOUND = False

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa


################################################################################
class ModBusTCPReader(Reader):
    """
    Read data from Modbus TCP devices.

    Supports:
      - single-slave (legacy) mode
      - multi-slave / multi-function scan files
      - holding/input registers, coils, discrete inputs
      - text or raw-bytes output
      - partial failure tolerance
      - non-fatal connection failures
    """

    _FUNCTION_MAP = {
        "holding_registers": "read_holding_registers",
        "input_registers": "read_input_registers",
        "coils": "read_coils",
        "discrete_inputs": "read_discrete_inputs",
    }

    ############################
    def __init__(self,
                 registers=None,
                 host="localhost",
                 port=502,
                 scan_file=None,
                 slave=1,
                 function="holding_registers",
                 interval=10,
                 sep=" ",
                 encoding="utf-8",
                 encoding_errors="ignore",
                 **kwargs):

        super().__init__(encoding=encoding, encoding_errors=encoding_errors, **kwargs)

        if not MODBUS_MODULE_FOUND:
            raise RuntimeError(
                "Modbus functionality not available. Please install Python module pyModbusTCP."
            )

        self.sep = sep if encoding is not None else None
        self.interval = interval
        self._lock = Lock()
        self._next_read_time = 0.0

        self.client = ModbusClient(
            host=host,
            port=port,
            auto_open=True,
            auto_close=True,
        )

        self.polls = []

        if scan_file:
            self._load_scan_file(scan_file)
        else:
            # Legacy single-poll behavior
            if registers is None:
                raise ValueError("registers required when scan_file not provided")

            self.polls.append({
                "slave": slave,
                "function": function,
                "registers": self._parse_registers(registers)
            })

    ############################
    def _parse_register_spec(self, spec):
        """Parse a single register spec into (start, count) tuple."""
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
        """Parse register specification into [(start, count), ...] blocks."""
        if isinstance(registers, list):
            return self._validate_blocks(registers)

        if not isinstance(registers, str):
            raise TypeError("registers must be a string or list")

        blocks = []
        for spec in registers.split(","):
            spec = spec.strip()
            if spec:
                blocks.append(self._parse_register_spec(spec))

        if not blocks:
            raise ValueError("No valid registers specified")

        return blocks

    ############################
    def _load_scan_file(self, path):
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)

        if "polls" not in cfg:
            raise ValueError("scan_file must contain 'polls' list")

        for poll in cfg["polls"]:
            self.polls.append({
                "slave": poll["slave"],
                "function": poll.get("function", "holding_registers"),
                "registers": self._parse_registers(poll["registers"]),
            })

    ############################
    def _format_record(self, readings):
        """
        Flatten nested register/coil values into a single record.

        - encoding=None:
            - registers -> 16-bit unsigned big-endian
            - coils -> packed bits
        - otherwise:
            - text with sep, 'nan' placeholders
        """
        if readings is None:
            return None

        flat_values = [val for block in readings if block for val in block]

        if self.encoding is None:
            if not flat_values:
                return b""

            first_val = next((v for v in flat_values if v is not None), 0)

            # Coils / discrete inputs
            if isinstance(first_val, (bool, int)) and all(
                v in (0, 1, True, False, None) for v in flat_values
            ):
                byte_vals = []
                current = 0
                for i, bit in enumerate(flat_values):
                    current |= (1 if bit else 0) << (i % 8)
                    if i % 8 == 7:
                        byte_vals.append(current)
                        current = 0
                if len(flat_values) % 8:
                    byte_vals.append(current)
                return bytes(byte_vals)

            # Registers
            return b"".join(
                int(val or 0).to_bytes(2, byteorder="big", signed=False)
                for val in flat_values
            )

        # Text mode
        text_values = [str(val) if val is not None else "nan" for val in flat_values]
        return self._encode_str(self.sep.join(text_values))

    ############################
    def read(self):
        """
        Read all configured polls.

        Returns:
          - list[str|bytes|None] for each poll
          - None in place of any poll that cannot be read
        """
        with self._lock:
            now = time.monotonic()
            if now < self._next_read_time:
                time.sleep(self._next_read_time - now)

            start_time = time.monotonic()
            results = []

            for poll in self.polls:
                slave = poll["slave"]
                func_name = self._FUNCTION_MAP.get(poll["function"])

                if not func_name:
                    logging.warning(
                        "Invalid function for slave=%s: %s",
                        slave, poll["function"]
                    )
                    total = sum(c for _, c in poll["registers"])
                    results.append([[None] * total])
                    continue

                func = getattr(self.client, func_name)
                poll_readings = []

                try:
                    for start, count in poll["registers"]:
                        block = func(start, count, unit_id=slave)
                        if block is None:
                            logging.warning(
                                "Failed to read slave=%d addr=%d:%d",
                                slave, start, count
                            )
                            poll_readings.append([None] * count)
                        else:
                            poll_readings.append(block)

                    results.append(poll_readings)

                except (OSError, AttributeError, ValueError, ConnectionError) as exc:
                    logging.warning(
                        "Modbus TCP connection error for slave=%d: %s", slave, exc
                    )
                    results.append(None)  # Entire poll failed, not fatal

            self._next_read_time = start_time + self.interval

            # Format records, preserving None for failed polls
            formatted = [self._format_record(r) if r is not None else None for r in results]

            # Prepend slave info for text mode
            if self.encoding is not None:
                formatted = [
                    self._encode_str(f"slave {poll['slave']}:{self.sep}{line.decode(self.encoding) if isinstance(line, bytes) else line}")
                    if line is not None else None
                    for poll, line in zip(self.polls, formatted)
                ]

            return formatted
