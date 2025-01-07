#!/usr/bin/env python3

import sys

import unittest
from unittest.mock import patch, MagicMock, call

sys.path.append('.')
from logger.readers.polled_serial_reader import PolledSerialReader  # noqa: E402


class TestPolledSerialReader(unittest.TestCase):
    def setUp(self):
        # Create a mock for the serial port within the test class
        self.mock_serial_instance = MagicMock()
        self.patcher = patch('serial.Serial', return_value=self.mock_serial_instance)
        self.patcher.start()
        self.mock_serial_instance.readline.return_value = b'Hello, World!\n'

    def tearDown(self):
        # Stop the patcher to clean up after tests
        self.patcher.stop()

    def test_with_start_and_stop_commands(self):
        start_cmd = "POWER ON"
        stop_cmd = "POWER OFF"
        pre_read_cmd = "INITIALIZE"
        reader = PolledSerialReader(port='/dev/testport', pre_read_cmd=pre_read_cmd,
                                    start_cmd=start_cmd, stop_cmd=stop_cmd)

        # Test that the start command was sent
        self.mock_serial_instance.write.assert_called_once_with(start_cmd.encode())
        self.mock_serial_instance.write.reset_mock()

        # Call read to simulate usage
        result = reader.read()
        self.assertEqual(result, 'Hello, World!')

        # Verify pre_read_cmd and stop_cmd
        expected_calls = [call(pre_read_cmd.encode()), call(stop_cmd.encode())]
        del reader
        self.mock_serial_instance.write.assert_has_calls(expected_calls, any_order=False)
        self.mock_serial_instance.readline.assert_called_once()

    def test_with_no_start_or_stop_commands(self):
        pre_read_cmd = ["SETUP", "CONFIGURE"]
        reader = PolledSerialReader(port='/dev/testport', pre_read_cmd=pre_read_cmd)

        # Call read to simulate usage
        result = reader.read()
        self.assertEqual(result, 'Hello, World!')

        # Verify pre_read_cmds
        calls = [call(cmd.encode()) for cmd in pre_read_cmd]
        self.mock_serial_instance.write.assert_has_calls(calls, any_order=False)
        self.mock_serial_instance.readline.assert_called_once()

    def test_with_dict_of_commands(self):
        pre_read_cmd_dict = {"phase1": ["CONFIGURE", "TEST"], "phase2": ["START", "RUN"]}
        reader = PolledSerialReader(port='/dev/testport', pre_read_cmd=pre_read_cmd_dict)

        # Call read to simulate usage for first phase
        result_first = reader.read()
        self.assertEqual(result_first, 'Hello, World!')
        first_calls = [call(cmd.encode()) for cmd in pre_read_cmd_dict["phase1"]]
        self.mock_serial_instance.write.assert_has_calls(first_calls, any_order=False)
        self.mock_serial_instance.write.reset_mock()
        self.mock_serial_instance.readline.reset_mock()

        # Call read to simulate usage for second phase
        result_second = reader.read()
        self.assertEqual(result_second, 'Hello, World!')
        second_calls = [call(cmd.encode()) for cmd in pre_read_cmd_dict["phase2"]]
        self.mock_serial_instance.write.assert_has_calls(second_calls, any_order=False)
        self.mock_serial_instance.readline.assert_called_once()


if __name__ == '__main__':
    unittest.main()
