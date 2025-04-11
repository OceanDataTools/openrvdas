#!/usr/bin/env python3
import os
import sys
import socket
import tempfile
import atexit
import threading
from typing import Optional, Dict

# Add parent directory to path
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402

# Global reference counter for channels
_channel_refs: Dict[str, int] = {}
_lock = threading.Lock()


class SocketReader(Reader):
    """Reader class for socket-based IPC mechanism.

    Reads records from a Unix domain socket.
    """

    def __init__(self, channel: str, timeout: Optional[float] = None,
                 buffer_size: int = 4096, keep_binary: bool = False):
        """Initialize a Reader for the specified channel.

        Args:
            channel: A string identifier for the communication channel
            timeout: Maximum time to wait for a record when reading (None means wait forever)
            buffer_size: Max record size to expect
            keep_binary: If true, don't convert received record to string
        """
        self.timeout = timeout
        self.buffer_size = buffer_size
        self.keep_binary = keep_binary

        # Create a unique socket path based on the channel name
        import hashlib
        channel_hash = hashlib.md5(channel.encode()).hexdigest()[:8]
        self.channel = channel

        # Set socket path in temp directory to avoid permission issues
        temp_dir = tempfile.gettempdir()
        self.socket_path = os.path.join(temp_dir, f'ipc_socket_{channel_hash}')

        # Socket for receiving data
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

        try:
            # Try to bind to the socket path
            self.sock.bind(self.socket_path)
        except OSError:
            # If socket already exists but no process is bound to it
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
                self.sock.bind(self.socket_path)
            else:
                raise

        # Set socket timeout
        if self.timeout is not None:
            self.sock.settimeout(self.timeout)

        # Update reference counter
        with _lock:
            _channel_refs[self.channel] = _channel_refs.get(self.channel, 0) + 1

        # Register cleanup on exit
        atexit.register(self.close)

    def read(self) -> str:
        """Read a record from the channel, blocking until one is available.

        Returns:
            str: The data that was read

        Raises:
            TimeoutError: If no data is available within the timeout period
        """
        try:
            record, _ = self.sock.recvfrom(self.buffer_size)
            if not self.keep_binary:
                record = record.decode('utf-8')
            return record
        except socket.timeout:
            raise TimeoutError('No data available within timeout period')

    def close(self):
        """Clean up resources and potentially clean up the channel."""
        if not hasattr(self, 'sock') or self.sock is None:
            # Already closed
            return

        self.sock.close()
        self.sock = None

        # Decrement reference counter and cleanup if this is the last reference
        with _lock:
            _channel_refs[self.channel] = _channel_refs.get(self.channel, 1) - 1
            if _channel_refs[self.channel] <= 0:
                if os.path.exists(self.socket_path):
                    os.unlink(self.socket_path)

                # Remove from reference counter
                _channel_refs.pop(self.channel, None)

    def __del__(self):
        """Ensure cleanup happens."""
        self.close()
