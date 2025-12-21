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

    This reader polls one or more Modbus slaves at a fixed interval, reading
    registers, coils, or inputs and returning the results as formatted text
    records. The serial port is kept open between reads and automatically
    reconnected if communication fails.

    The reader supports two operating modes:

    1. Legacy single-slave mode
       -------------------------
       If ``scan_file`` is not provided, the reader polls a single Modbus slave
       using the ``slave`` and ``registers`` arguments.

       Example:
           ModBusSerialReader(
               port="/dev/ttyUSB0",
               slave=1,
               registers="0:9,20:21",
               interval=5
           )

       This will read:
           - registers 0–9 (10 registers)
           - registers 20–21 (2 registers)
       from slave ID 1 every 5 seconds.

    2. Scan file (multi-slave) mode
       ------------------------------
       If ``scan_file`` is provided, polling behavior is defined by a YAML file
       describing one or more poll groups. Each poll group specifies:
           - slave ID
           - Modbus function
           - register ranges

       Example scan file:
           polls:
             - slave: 1
               function: holding_registers
               registers: "0:9,20:21"

             - slave: 2
               function: input_registers
               registers:
                 - [0, 4]
                 - [10, 2]

       Each call to ``read()`` iterates through all poll groups in order and
       returns one output record per slave.

    Supported Modbus functions:
        - "holding_registers"
        - "input_registers"
        - "coils"
        - "discrete_inputs"

    Register specification:
        Registers may be defined as:
            - A comma-separated string (e.g. "0:9,20")
            - A list of (start, count) tuples

    Output format:
        Each call to ``read()`` returns a string containing one or more
        lines, one per slave, formatted as:

            slave <id>: <value1> <value2> <value3> ...

        Example:
            slave 1: 100 101 102
            slave 2: 55 56 57

        If a read fails or times out, the corresponding values are returned
        as "nan" placeholders.

    Thread safety:
        Access to the serial port is protected by an internal lock, making
        this reader safe to use in threaded environments.

    Lifecycle behavior:
        - The serial port is opened lazily on the first read
        - The connection is reused between reads
        - Automatic reconnection occurs on failure
        - The port may be explicitly closed by calling ``stop()``
        - The destructor ensures the port is closed on cleanup

    Raises:
        RuntimeError:
            If pymodbus is not installed or Modbus functionality is unavailable.
    """
    def __init__(self,
                 registers,
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
            # Legacy single-slave behavior
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
            logging.error("ModBusSerialReader: unable to open serial port")

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
        - If encoding=None:
            - Registers → 16-bit unsigned big-endian
            - Coils/discrete_inputs → packed bits
            - None values → 0
        - Otherwise: convert to text and encode with _encode_str, using self.sep
        """
        # Flatten all readings
        flat_values = [val for block in readings if block for val in block]

        if self.encoding is None:
            if not flat_values:
                return b""

            first_val = next((v for v in flat_values if v is not None), 0)

            # Coils/discrete inputs: bool or 0/1
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
                # Registers
                return b"".join(int(val or 0).to_bytes(2, byteorder="big", signed=False) for val in flat_values)

        # Text output (use self.sep, guaranteed not None)
        text_values = [str(val) if val is not None else "nan" for val in flat_values]
        text_record = self.sep.join(text_values)
        return self._encode_str(text_record)

    ############################
    def read(self):
        """Read all configured polls and return a list of formatted records per slave.

        Returns:
            list[bytes|str] | None:
                - None if the connection could not be established
                - List of raw bytes (encoding=None) or encoded strings per slave otherwise
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
                            if resp is None or resp.isError():
                                logging.warning("Failed to read slave=%d addr=%d:%d", slave, start, count)
                                readings.append([None] * count)
                            else:
                                values = getattr(resp, "registers", getattr(resp, "bits", None))
                                readings.append(values or [None] * count)
                        except (ModbusException, OSError, ConnectionError, ValueError, AttributeError) as exc:
                            logging.error("Modbus read error slave=%d addr=%d:%d: %s", slave, start, count, exc)
                            readings.append([None] * count)
                            self._connected = False

                # Flatten and format readings for this poll
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
