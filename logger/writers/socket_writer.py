#!/usr/bin/env python3
import os
import sys
import socket
import tempfile
import atexit
import threading
from typing import Any, Dict

# Add parent directory to path
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.writer import Writer  # noqa: E402

# Global reference counter for channels
_channel_refs: Dict[str, int] = {}
_lock = threading.Lock()


class SocketWriter(Writer):
    """Writer class for socket-based IPC mechanism.

    Writes records to a Unix domain socket.
    """

    def __init__(self, channel: str, **kwargs):
        """Initialize a Writer for the specified channel.

        Args:
            channel: A string identifier for the communication channel
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        # Create a unique socket path based on the channel name
        import hashlib
        channel_hash = hashlib.md5(channel.encode()).hexdigest()[:8]
        self.channel = channel

        # Set socket path in temp directory to avoid permission issues
        temp_dir = tempfile.gettempdir()
        self.socket_path = os.path.join(temp_dir, f'ipc_socket_{channel_hash}')

        # Socket for sending data
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

        # Update reference counter
        with _lock:
            _channel_refs[self.channel] = _channel_refs.get(self.channel, 0) + 1

        # Register cleanup on exit
        atexit.register(self.close)

    def write(self, record: Any) -> bool:
        """Write a record to the channel.

        If no Reader is waiting, the record is discarded.

        Args:
            record: The data to write (will be converted to bytes)

        Returns:
            bool: True if data was written, False if it was discarded
        """
        if isinstance(record, str):
            record = record.encode('utf-8')
        elif not isinstance(record, bytes):
            record = str(record).encode('utf-8')

        # Check if the socket path exists (indicating a receiver)
        if not os.path.exists(self.socket_path):
            # No reader is waiting, discard the message
            return False

        # Send the record
        try:
            self.sock.sendto(record, self.socket_path)
            return True
        except (ConnectionRefusedError, FileNotFoundError):
            # No reader is available
            return False

    def close(self):
        """Clean up resources."""
        if not hasattr(self, 'sock') or self.sock is None:
            # Already closed
            return

        self.sock.close()
        self.sock = None

        # Decrement reference counter
        with _lock:
            _channel_refs[self.channel] = _channel_refs.get(self.channel, 1) - 1

    def __del__(self):
        """Ensure cleanup happens."""
        self.close()
