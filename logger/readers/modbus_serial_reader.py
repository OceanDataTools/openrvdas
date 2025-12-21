#!/usr/bin/env python3

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

    Supports:
      - single-slave (legacy) mode
      - multi-slave / multi-function scan files
      - holding/input registers, coils, discrete inputs
      - text or raw-bytes output
      - partial failure tolerance
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
            logging.warning("ModBusSerialReader: unable to open serial port")

        return self._connected

    ############################
    def _load_scan_file(self, path):
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
    def _format_record(self, readings: list[list[int | bool]]) -> bytes | str:
        """
        Flatten nested register/coil values into a single record.

        - encoding=None:
            - Registers → 16-bit unsigned big-endian
            - Coils/discrete_inputs → packed bits
            - None values → 0
        - Otherwise: convert to text and encode with _encode_str, using self.sep
        """
        flat_values = [val for block in readings if block for val in block]

        if self.encoding is None:
            if not flat_values:
                return b""

            first_val = next((v for v in flat_values if v is not None), 0)

            if isinstance(first_val, (bool, int)) and all(v in (0, 1, None, True, False) for v in flat_values):
                byte_vals = []
                current_byte = 0
                for i, bit in enumerate(flat_values):
                    bit_val = 1 if bit else 0
                    current_byte |= bit_val << (i % 8)
                    if (i % 8) == 7:
                        byte_vals.append(current_byte)
                        current_byte = 0
                if len(flat_values) % 8 != 0:
                    byte_vals.append(current_byte)
                return bytes(byte_vals)
            else:
                return b"".join(int(val or 0).to_bytes(2, byteorder="big", signed=False) for val in flat_values)

        text_values = [str(val) if val is not None else "nan" for val in flat_values]
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
                records = [None for _ in self.polls]
                self._next_read_time = start_time + self.interval
                return records

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
                            self._connected = False

                record = self._format_record(readings)
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
