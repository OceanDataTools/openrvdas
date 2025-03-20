#!/usr/bin/env python3
import logging
import unittest
import time
import sys
import os
import threading
from typing import List

# Add parent directory to path
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))
from logger.readers.socket_reader import SocketReader  # noqa: E402
from logger.writers.socket_writer import SocketWriter  # noqa: E402


class TestSocketReader(unittest.TestCase):
    """Test cases for the SocketReader class."""

    def setUp(self):
        """Set up test environment."""
        # Use a unique channel name for each test
        self.channel = f'test_channel_{time.time()}'
        self.reader = None
        self.writers: List[SocketWriter] = []

    def tearDown(self):
        """Clean up test environment."""
        # Close reader
        if self.reader:
            self.reader.close()

        # Close all writers
        for writer in self.writers:
            writer.close()

        # Wait a bit to ensure cleanup happens
        time.sleep(0.1)

    def test_initialization(self):
        """Test that a reader can be initialized."""
        reader = SocketReader(self.channel)
        self.assertIsNotNone(reader)
        self.reader = reader

    def test_read_timeout(self):
        """Test that read times out appropriately."""
        self.reader = SocketReader(self.channel, timeout=0.1)

        # Read with a short timeout - should raise TimeoutError
        with self.assertRaises(TimeoutError):
            self.reader.read()

    def test_read_data(self):
        """Test reading data from a writer."""
        self.reader = SocketReader(self.channel, timeout=0.5)

        # Give reader time to initialize
        time.sleep(0.1)

        writer = SocketWriter(self.channel)
        self.writers.append(writer)

        # Write a message
        message = 'Test message'
        writer.write(message)

        # Read the message
        received = self.reader.read()
        self.assertEqual(received.decode('utf-8'), message)

    def test_read_binary(self):
        """Test reading binary data."""
        self.reader = SocketReader(self.channel, timeout=0.5)

        # Give reader time to initialize
        time.sleep(0.1)

        writer = SocketWriter(self.channel)
        self.writers.append(writer)

        # Write binary data
        binary_data = b'\x00\x01\x02\x03\x04\x05'
        writer.write(binary_data)

        # Read the data
        received = self.reader.read()
        self.assertEqual(received, binary_data)

    def test_multiple_messages(self):
        """Test reading multiple messages in sequence."""
        self.reader = SocketReader(self.channel, timeout=0.5)

        # Give reader time to initialize
        time.sleep(0.1)

        writer = SocketWriter(self.channel)
        self.writers.append(writer)

        # Write multiple messages
        messages = ['Message 1', 'Message 2', 'Message 3']

        for msg in messages:
            writer.write(msg)
            # Read message immediately after writing
            received = self.reader.read()
            self.assertEqual(received.decode('utf-8'), msg)

    def test_multiple_writers(self):
        """Test reading from multiple writers."""
        self.reader = SocketReader(self.channel, timeout=0.5)

        # Give reader time to initialize
        time.sleep(0.1)

        writer1 = SocketWriter(self.channel)
        writer2 = SocketWriter(self.channel)
        self.writers.extend([writer1, writer2])

        # Writers send different messages
        msg1 = 'Message from writer 1'
        msg2 = 'Message from writer 2'

        writer1.write(msg1)
        received1 = self.reader.read()
        self.assertEqual(received1.decode('utf-8'), msg1)

        writer2.write(msg2)
        received2 = self.reader.read()
        self.assertEqual(received2.decode('utf-8'), msg2)

    def test_reader_before_writer(self):
        """Test creating reader before writer."""
        self.reader = SocketReader(self.channel, timeout=1.0)

        # Start a read with timeout in a separate thread
        result = [None]
        exception = [None]

        def read_with_timeout():
            try:
                result[0] = self.reader.read()
            except Exception as e:
                exception[0] = e

        thread = threading.Thread(target=read_with_timeout)
        thread.start()

        # Give the thread time to start reading
        time.sleep(0.1)

        # Now create a writer and send a message
        writer = SocketWriter(self.channel)
        self.writers.append(writer)
        test_msg = 'Late writer message'
        writer.write(test_msg)

        # Wait for thread to complete
        thread.join()

        # Check result
        self.assertIsNone(exception[0], f'Exception occurred: {exception[0]}')
        self.assertEqual(result[0].decode('utf-8'), test_msg)

    def test_automatic_cleanup(self):
        """Test that resources are cleaned up when reader is closed."""
        # Create a reader with a unique channel
        channel = f'cleanup_test_{time.time()}'
        reader = SocketReader(channel)

        # Extract the path
        socket_path = reader.socket_path

        # Verify resource exists
        self.assertTrue(os.path.exists(socket_path))

        # Close the reader
        reader.close()

        # Wait a bit for cleanup
        time.sleep(0.1)

        # Since this is the only reference, resources should be cleaned up
        self.assertFalse(os.path.exists(socket_path))

    def test_shared_cleanup(self):
        """Test that cleanup works with both reader and writer."""
        channel = f'shared_cleanup_{time.time()}'

        # Create both reader and writer
        reader = SocketReader(channel)
        writer = SocketWriter(channel)

        # Get path for validation
        socket_path = reader.socket_path

        # Resource should exist
        self.assertTrue(os.path.exists(socket_path))

        # Close reader but keep writer
        reader.close()

        # Wait a bit for cleanup
        time.sleep(0.1)

        # Resource should be gone (reader is the socket owner)
        self.assertFalse(os.path.exists(socket_path))

        # Now close writer
        writer.close()


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
