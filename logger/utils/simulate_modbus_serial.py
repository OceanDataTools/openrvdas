#!/usr/bin/env python3

import logging
import os
import sys
import subprocess
import threading
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402

class SimModbusSerial:
    """Simulate a serial Modbus device using a virtual port and feed test register values."""

    def __init__(self, port, registers=None, interval=1.0, baudrate=9600, timeout=None):
        """
        port        The virtual serial port to create.
        registers   List of lists, each inner list is a register block to return.
        interval    Seconds between each poll (simulate device timing)
        """
        self.read_port = port
        self.write_port = port + "_in"
        self.registers = registers or [[0] * 10]  # default 10 registers
        self.interval = interval
        self.quit = False

        self.serial_params = {
            'baudrate': baudrate,
            'timeout': timeout,
        }

        # detect socat path
        self.socat_path = None
        for path in ['/usr/bin/socat', '/usr/local/bin/socat', '/opt/homebrew/bin/socat']:
            if os.path.isfile(path):
                self.socat_path = path
                break
        if not self.socat_path:
            raise RuntimeError('Executable "socat" not found on path.')

    def _run_socat(self):
        """Internal: run socat to create virtual serial ports."""
        verbose = "-d"
        write_port_params = f"pty,link={self.write_port},raw,echo=0"
        read_port_params = f"pty,link={self.read_port},raw,echo=0"

        cmd = [self.socat_path, verbose, read_port_params, write_port_params]

        try:
            logging.info("Starting socat: %s", " ".join(cmd))
            proc = subprocess.Popen(cmd)
            while not self.quit and proc.poll() is None:
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if proc.poll() is None:
                proc.kill()
            logging.info("Finished socat: %s", " ".join(cmd))

    def run(self, loop=False):
        """Feed Modbus register data to the virtual serial port."""
        self.socat_thread = threading.Thread(target=self._run_socat, daemon=True)
        self.socat_thread.start()
        time.sleep(0.2)  # allow socat to create ports

        while not self.quit:
            for block in self.registers:
                if self.quit:
                    break

                # skip None blocks (simulate timeout)
                if block is None:
                    time.sleep(self.interval)
                    continue

                # convert registers to bytes (Modbus big-endian 16-bit)
                try:
                    data_bytes = b"".join(r.to_bytes(2, byteorder='big', signed=False) for r in block)
                except Exception as e:
                    logging.error("Invalid register block %s: %s", block, e)
                    continue

                try:
                    with open(self.write_port, "wb") as f:
                        f.write(data_bytes)
                except Exception as e:
                    logging.error("Error writing to virtual Modbus port: %s", e)
                    self.quit = True
                    break

                time.sleep(self.interval)

            if not loop:
                break

        self.quit = True
