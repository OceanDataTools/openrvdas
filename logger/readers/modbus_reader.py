#!/usr/bin/env python3

import logging
import sys
import time
from threading import Lock

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

        if isinstance(registers, str) and registers.endswith(":"):
            raise ValueError('Registers value cannot end with an ambiguous '
                             'maximum register number (i.e. "5:").')

        self.registers = self._validate_blocks(self._parse_registers(registers))
        self.sep = sep
        self.interval = interval
        self._lock = Lock()
        self._next_read_time = 0.0

        self.client = ModbusClient(host=host, port=port, auto_open=True, auto_close=True)


    ############################
    def _parse_register_spec(self, spec):
        """
        Parse a single register spec into a (start, count) tuple.
        """
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
        """
        Parse register specification into [(start, count), ...] blocks.
        """
        if isinstance(registers, list):
            return self._validate_blocks(registers)

        if not isinstance(registers, str):
            raise TypeError("registers must be a string, list, or None")

        blocks = []
        for spec in registers.split(","):
            spec = spec.strip()
            if not spec:
                continue
            blocks.append(self._parse_register_spec(spec))

        if not blocks:
            raise ValueError("No valid registers specified")

        return blocks


    def _format_record(self, readings: list[list[int]]) -> bytes | str:
        """
        Convert nested list of register values into a single record.
        - If encoding=None: return raw bytes (16-bit big-endian)
        - Otherwise, convert to text and encode using _encode_str
        """
        flat_values = [val for block in readings if block for val in block if val is not None]

        if self.encoding is None:
            # raw bytes: 16-bit unsigned big-endian
            return b''.join(val.to_bytes(2, byteorder='big', signed=False)
                            for val in flat_values)

        # Convert to text string first
        text_record = self.sep.join(str(val) for val in flat_values)
        return self._encode_str(text_record)


    ############################
    def read(self):
        """
        Read the specified registers. Return values as a text record. Wait the
        specified interval before reading again. Logs partial failures.
        """
        with self._lock:
            now = time.monotonic()
            
            if now < self._next_read_time:
                time.sleep(self._next_read_time - now)
            
            start_time = time.monotonic()
            readings = []

            for reg_start, count in self.registers:
                try:
                    block = self.client.read_holding_registers(reg_start, count)
            
                    if block is None:
                        logging.warning("Failed to read registers %d:%d", reg_start, count)
                        block = []
            
                    readings.append(block)
            
                except (OSError, AttributeError, ValueError, ConnectionError) as exc:
                    logging.error("ModBusReader registers %d:%d error: %s", reg_start, count, exc)
                    readings.append([])

            try:
                record = self._format_record(readings)
            except Exception as exc:
                logging.exception("Error formatting ModBus register record: %s", exc)
                record = None

            if record is not None:
                logging.debug("ModBusReader.read() received %d bytes: %s",
                    len(record) if isinstance(record, bytes) else len(str(record)),
                    readings
                )
            else:
                logging.debug("ModBusReader.read() returned None")

            self._next_read_time = start_time + self.interval

            return self._decode_bytes(record)
