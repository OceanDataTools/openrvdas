#!/usr/bin/env python3

import logging
import sys
import unittest
import tempfile
import yaml
import json
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

    ###########################################################################
    def make_mock_client(self, responses_by_function):
        """
        responses_by_function = {
            'read_holding_registers': [resp, resp, ...],
            'read_input_registers': [...],
            ...
        }
        """
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.close.return_value = True

        for func_name, responses in responses_by_function.items():

            def make_side_effect(queue):
                def side_effect(**kwargs):
                    return queue.pop(0) if queue else None
                return side_effect

            setattr(
                mock_client,
                func_name,
                MagicMock(side_effect=make_side_effect(responses.copy()))
            )

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

    ###########################################################################
    def make_response(self, slave, registers):
        if registers is None:
            return None

        class Response:
            def __init__(self, slave, regs):
                self.registers = regs
                self.slave = slave

            def isError(self):
                return False

        return Response(slave, registers)

    # ###########################################################################
    @patch("logger.readers.modbus_serial_reader.ModbusSerialClient")
    def test_read_register_blocks(self, mock_client_cls):

        responses = [ self.make_response(1, x) for x in SAMPLE_REGISTERS ]

        mock_client_cls.return_value = self.make_mock_client({
            "read_holding_registers": responses
        })

        reader = ModBusSerialReader(registers="0:2,3:5,6:8", port="/dev/ttyUSB0", interval=0.01)
        result = reader.read()
        expected = f"slave 1: {' '.join([str(x) if x != 'nan' else x for x in self.flatten_blocks(SAMPLE_REGISTERS)])}"
        self.assertEqual(expected, result)

    ###########################################################################
    @patch("logger.readers.modbus_serial_reader.ModbusSerialClient")
    def test_read_with_timeout(self, mock_client_cls):

        responses = [ self.make_response(1, x) for x in SAMPLE_TIMEOUT_REGISTERS ]

        mock_client_cls.return_value = self.make_mock_client({
            "read_holding_registers": responses
        })

        reader = ModBusSerialReader(registers="0:2,3:5,6:8,9:11", port="/dev/ttyUSB0", interval=0.01)
        result = reader.read()
        expected = f"slave 1: {' '.join([str(x) if x != None else 'nan' for x in self.flatten_blocks(SAMPLE_TIMEOUT_REGISTERS)])}"
        self.assertEqual(expected, result)

    ###########################################################################
    @patch("logger.readers.modbus_serial_reader.ModbusSerialClient")
    def test_unicode_handling(self, mock_client_cls):

        responses = [
            self.make_response(1, [0xFF, 0xFE, 0xABCD])
        ]

        mock_client_cls.return_value = self.make_mock_client({
            "read_holding_registers": responses
        })

        reader = ModBusSerialReader(registers="0:2", port="/dev/ttyUSB0", interval=0.01)
        result = reader.read()
        expected = f"slave 1: {' '.join([str(x) for x in [255, 254, 43981]])}"
        self.assertEqual(expected, result)

    ###########################################################################
    @patch("logger.readers.modbus_serial_reader.ModbusSerialClient")
    def test_poll_file_single_slave(self, mock_client_cls):
        yaml_cfg = {
            "polls": [
                {
                    "slave": 1,
                    "function": "holding_registers",
                    "registers": "0:2"
                }
            ]
        }

        responses = [
            self.make_response(1, [10, 20, 30])
        ]

        mock_client_cls.return_value = self.make_mock_client({
            "read_holding_registers": responses
        })

        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            yaml.dump(yaml_cfg, f)
            fname = f.name

        reader = ModBusSerialReader(scan_file=fname, interval=0)
        result = reader.read()
        expected = f"slave 1: {' '.join([str(x) for x in [10, 20, 30]])}"
        self.assertEqual(expected, result)

    ###########################################################################
    @patch("logger.readers.modbus_serial_reader.ModbusSerialClient")
    def test_poll_file_multiple_slaves(self, mock_client_cls):
        yaml_cfg = {
            "polls": [
                {
                    "slave": 1,
                    "function": "holding_registers",
                    "registers": "0:1"
                },
                {
                    "slave": 2,
                    "function": "holding_registers",
                    "registers": "10:11"
                }
            ]
        }

        responses = [
            self.make_response(1,[1, 2]),
            self.make_response(2, [100, 200])
        ]

        mock_client_cls.return_value = self.make_mock_client({
            "read_holding_registers": responses
        })

        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            yaml.dump(yaml_cfg, f)
            fname = f.name

        reader = ModBusSerialReader(scan_file=fname, interval=0)
        result = reader.read()
        expected = f"slave 1: {' '.join([str(x) for x in [1, 2]])}\n"\
                   f"slave 2: {' '.join([str(x) for x in [100, 200]])}"
        self.assertEqual(expected, result)

    # ###########################################################################
    @patch("logger.readers.modbus_serial_reader.ModbusSerialClient")
    def test_poll_file_mixed_function_codes(self, mock_client_cls):
        yaml_cfg = {
            "polls": [
                {
                    "slave": 1,
                    "function": "holding_registers",
                    "registers": "0:1"
                },
                {
                    "slave": 1,
                    "function": "input_registers",
                    "registers": "5:6"
                }
            ]
        }

        mock_client_cls.return_value = self.make_mock_client({
            "read_holding_registers": [self.make_response(1, [1, 2])],
            "read_input_registers": [self.make_response(1, [9, 8])]
        })

        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            yaml.dump(yaml_cfg, f)
            fname = f.name

        reader = ModBusSerialReader(scan_file=fname, interval=0)
        result = reader.read()
        expected = f"slave 1: {' '.join([str(x) for x in [1, 2]])}\n"\
                   f"slave 1: {' '.join([str(x) for x in [9, 8]])}"
        self.assertEqual(expected, result)

    ###########################################################################
    @patch("logger.readers.modbus_serial_reader.ModbusSerialClient")
    def test_unknown_function_returns_nan(self, mock_client_cls):
        yaml_cfg = {
            "polls": [
                {
                    "slave": 1,
                    "function": "invalid_function",
                    "registers": "0:2"
                }
            ]
        }

        mock_client_cls.return_value = self.make_mock_client({})

        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            yaml.dump(yaml_cfg, f)
            fname = f.name

        reader = ModBusSerialReader(scan_file=fname, interval=0)
        result = reader.read()
        expected = f"slave 1: {' '.join(['nan']*3)}"
        self.assertEqual(expected, result)


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
