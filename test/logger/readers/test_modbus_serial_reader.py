#!/usr/bin/env python3

import logging
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append('.')  # ensure modules are importable

from logger.readers.modbus_serial_reader import ModBusSerialReader  # noqa: E402

# Test data
SAMPLE_REGISTERS = [
    [100, 200, 300],
    [400, 500, 600],
    [700, 800, 900]
]

SAMPLE_TIMEOUT_REGISTERS = [
    [10, 20, 30],
    None,
    None,
    [40, 50, 60]
]


class TestModBusSerialReader(unittest.TestCase):

    def make_mock_client(self, register_blocks):
        """Return a mock Modbus client for given register blocks."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.close.return_value = True

        # Prepare responses
        responses = []
        for block in register_blocks:
            if block is None:
                responses.append(None)
            else:
                class Response:
                    def __init__(self, registers):
                        self.registers = registers
                        self.isError = lambda: False
                responses.append(Response(block))

        def side_effect(address, count, **kwargs):
            return responses.pop(0) if responses else None

        mock_client.read_holding_registers.side_effect = side_effect
        return mock_client

    def flatten_blocks(self, blocks, default_size=3):
        """Flatten register blocks, replacing None with lists of Nones."""
        flat = []
        for block in blocks:
            if block is None:
                flat.extend([None] * default_size)
            else:
                flat.extend(block)
        return flat

    @patch("logger.readers.modbus_serial_reader.ModbusSerialClient")
    def test_read_register_blocks(self, mock_client_cls):
        mock_client_cls.return_value = self.make_mock_client(SAMPLE_REGISTERS)

        reader = ModBusSerialReader(registers="0:2,3:5,6:8", port="/dev/ttyUSB0", interval=0.01)
        result_text = reader.read()
        result_list = [int(x) for x in result_text.split(reader.sep)]
        expected = self.flatten_blocks(SAMPLE_REGISTERS)
        self.assertEqual(expected, result_list)

    @patch("logger.readers.modbus_serial_reader.ModbusSerialClient")
    def test_read_with_timeout(self, mock_client_cls):
        mock_client_cls.return_value = self.make_mock_client(SAMPLE_TIMEOUT_REGISTERS)

        reader = ModBusSerialReader(registers="0:2,3:5,6:8,9:11", port="/dev/ttyUSB0", interval=0.01)
        result_text = reader.read()
        result_list = [int(x) if x != "nan" else None for x in result_text.split(reader.sep)]
        expected = self.flatten_blocks(SAMPLE_TIMEOUT_REGISTERS)
        self.assertEqual(expected, result_list)

    @patch("logger.readers.modbus_serial_reader.ModbusSerialClient")
    def test_unicode_handling(self, mock_client_cls):
        registers = [[0xFF, 0xFE, 0xABCD]]
        mock_client_cls.return_value = self.make_mock_client(registers)

        reader = ModBusSerialReader(registers="0:3", port="/dev/ttyUSB0", interval=0.01)
        result_text = reader.read()
        result_list = [int(x) for x in result_text.split(reader.sep)]
        self.assertEqual(registers[0], result_list)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity', default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)
    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main()
