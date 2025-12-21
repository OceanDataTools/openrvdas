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
                 eol="\n",
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

        self.sep = sep
        self.eol = eol
        self.interval = interval
        self._next_read_time = 0.0

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

    def _parse_registers(self, registers):
        if registers is None:
            return [(0, 10)]

        if isinstance(registers, list):
            return registers

        blocks = []
        for reg in registers.split(","):
            reg = reg.strip()
            if ":" in reg:
                start, end = reg.split(":")
                start = int(start) if start else 0
                end = int(end)
                if end < start:
                    raise ValueError(f"Bad register range {reg}")
                blocks.append((start, end - start + 1))
            else:
                blocks.append((int(reg), 1))
        return blocks

    ############################
    def read(self):
        total_regs = sum(
            count
            for poll in self.polls
            for _, count in poll["registers"]
        )

        nan_record = self.sep.join(["nan"] * total_regs)

        with self._lock:

            now = time.monotonic()

            # Enforce polling interval BEFORE the request
            if now < self._next_read_time:
                time.sleep(self._next_read_time - now)

            start = time.monotonic()

            if not self._client_connected():
                return nan_record

            results = []

            for poll in self.polls:
                slave = poll["slave"]
                func_name = self._FUNCTION_MAP.get(poll["function"])

                record = {
                    "id": slave,
                    "values": []
                }

                if not func_name:
                    logging.warning(f"Invalid function slave={slave} function={poll['function']}")
                    total = sum(c for _, c in poll["registers"])
                    record["values"].extend(["nan"] * total)
                    results.append(record)
                    continue

                func = getattr(self.client, func_name)

                for start, count in poll["registers"]:
                    try:
                        resp = func(address=start, count=count, slave=slave)

                        if resp is None or resp.isError():
                            record["values"].extend(["nan"] * count)
                        else:
                            values = getattr(resp, "registers", None)
                            if not values:
                                record["values"].extend(["nan"] * count)
                            else:
                                record["values"].extend(str(v) for v in values)

                    except Exception as exc:
                        logging.error(f"Modbus error slave={slave} addr={start}: {exc}")
                        record.values.extend(["nan"] * count)
                        self._connected = False

                results.append(record)

            self._next_read_time = start + self.interval

            return self.eol.join([
                                f"slave {record['id']}:{self.sep}{self.sep.join(record['values'])}"
                                for record in results
                            ])

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
