#!/usr/bin/env python3
import logging
import unittest
import time
import sys
from typing import List

# Add parent directory to path
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(dirname(realpath(__file__))))))
from logger.writers.socket_writer import SocketWriter  # noqa: E402
from logger.readers.socket_reader import SocketReader  # noqa: E402


class TestSocketWriter(unittest.TestCase):
    """Test cases for the SocketWriter class."""

    def setUp(self):
        """Set up test environment."""
        # Use a unique channel name for each test
        self.channel = f'test_channel_{time.time()}'
        self.writer = None
        self.readers: List[SocketReader] = []

    def tearDown(self):
        """Clean up test environment."""
        # Close writer
        if self.writer:
            self.writer.close()

        # Close all readers
        for reader in self.readers:
            reader.close()

        # Wait a bit to ensure cleanup happens
        time.sleep(0.1)

    def test_initialization(self):
        """Test that a writer can be initialized."""
        writer = SocketWriter(self.channel)
        self.assertIsNotNone(writer)
        self.writer = writer

    def test_write_string(self):
        """Test writing a string message."""
        reader = SocketReader(self.channel, timeout=0.5)
        self.readers.append(reader)

        # Give reader time to initialize
        time.sleep(0.1)

        self.writer = SocketWriter(self.channel)

        # Write a message
        message = 'Hello, world!'
        result = self.writer.write(message)

        # Verify write succeeded
        self.assertTrue(result)

        # Read the message back
        received = reader.read()
        self.assertEqual(received.decode('utf-8'), message)

    def test_write_bytes(self):
        """Test writing bytes."""
        reader = SocketReader(self.channel, timeout=0.5)
        self.readers.append(reader)

        # Give reader time to initialize
        time.sleep(0.1)

        self.writer = SocketWriter(self.channel)

        # Write bytes
        message = b'Binary data: \x00\x01\x02\x03'
        result = self.writer.write(message)

        # Verify write succeeded
        self.assertTrue(result)

        # Read the message back
        received = reader.read()
        self.assertEqual(received, message)

    def test_write_non_string(self):
        """Test writing non-string data."""
        reader = SocketReader(self.channel, timeout=0.5)
        self.readers.append(reader)

        # Give reader time to initialize
        time.sleep(0.1)

        self.writer = SocketWriter(self.channel)

        # Write an integer
        result = self.writer.write(42)

        # Verify write succeeded
        self.assertTrue(result)

        # Read the message back
        received = reader.read()
        self.assertEqual(received.decode('utf-8'), '42')

    def test_write_no_reader(self):
        """Test writing when no reader is available."""
        self.writer = SocketWriter(self.channel)

        # Write a message with no reader available
        message = 'Message to no one'
        result = self.writer.write(message)

        # Verify write was discarded
        self.assertFalse(result)

    def test_multiple_readers(self):
        """Test that multiple readers receive the same message."""
        reader1 = SocketReader(self.channel, timeout=0.5)
        reader2 = SocketReader(f'{self.channel}_second', timeout=0.5)
        self.readers.extend([reader1, reader2])

        # Give readers time to initialize
        time.sleep(0.1)

        # Create writers for each reader
        writer1 = SocketWriter(self.channel)
        writer2 = SocketWriter(f'{self.channel}_second')
        self.writer = writer1  # For cleanup in tearDown

        # Write message to first channel
        message1 = 'Message to first channel'
        writer1.write(message1)

        # First reader should receive it
        received1 = reader1.read()
        self.assertEqual(received1.decode('utf-8'), message1)

        # Write message to second channel
        message2 = 'Message to second channel'
        writer2.write(message2)

        # Second reader should receive it
        received2 = reader2.read()
        self.assertEqual(received2.decode('utf-8'), message2)

        # Close second writer
        writer2.close()

    def test_automatic_cleanup(self):
        """Test that writer properly releases resources."""
        # Create a writer
        channel = f'cleanup_test_{time.time()}'
        writer = SocketWriter(channel)

        # Verify writer was initialized
        self.assertIsNotNone(writer.sock)

        # Close the writer
        writer.close()

        # Verify resources were cleaned up
        self.assertIsNone(writer.sock)


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
