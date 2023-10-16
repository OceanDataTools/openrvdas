#!/usr/bin/env python3

import logging
import serial
import sys
import time

sys.path.append('.')
from logger.readers.serial_reader import SerialReader  # noqa: E402


################################################################################
class PolledSerialReader(SerialReader):
    """
    Read text records from a serial port.
    """

    def __init__(self,  port, baudrate=9600, bytesize=8, parity='N',
                 stopbits=1, timeout=None, xonxoff=False, rtscts=False,
                 write_timeout=None, dsrdtr=False, inter_byte_timeout=None,
                 exclusive=None, max_bytes=None, eol=None,
                 encoding='utf-8', encoding_errors='ignore',
                 start_cmd=None, pre_read_cmd=None, stop_cmd=None):
        """Extends the standard serial reader by allowing the user to define
        strings to send to the serial host on startup, before each read and
        just prior to the reader being destroyed.

        If start_cmd, pre_read_cmd or stop_cmd are lists of strings, send
        as sequential commands. The string ``__PAUSE__``, followed by a
        number, is interpreted as a command to pause for that many seconds
        prior to sending the next command.
        """
        self.start_cmd = start_cmd
        self.pre_read_cmd = pre_read_cmd
        self.stop_cmd = stop_cmd

        super().__init__(port=port, baudrate=baudrate, bytesize=bytesize,
                         parity=parity, stopbits=stopbits, timeout=timeout,
                         xonxoff=xonxoff, rtscts=rtscts, write_timeout=write_timeout,
                         dsrdtr=dsrdtr, inter_byte_timeout=inter_byte_timeout,
                         exclusive=exclusive, max_bytes=max_bytes, eol=eol,
                         encoding=encoding, encoding_errors=encoding_errors)

        if self.start_cmd:
            try:
                self._send_command(start_cmd)
            except serial.serialutil.SerialException as e:
                logging.error(str(e))

    ############################
    def _send_command(self, command):
        """Send a command, or list of commands to the serial port."""
        if not command:
            return
        if type(command) is str:
            # Do some craziness to unescape escape sequences like '\n'
            self.serial.write(self._encode_str(command, unescape=True))
            return

        if not type(command) is list:
            raise ValueError('PolledSerialReader commands must be either strings or '
                             'lists. Received: type %s: %s' % (type(command), command))

        # Iterate through commands, pausing as necessary
        for cmd in command:
            # Is it our special 'pause' command?
            if cmd.find('__PAUSE__') == 0:
                pause_cmd = cmd.split()
                if len(pause_cmd) == 1:
                    pause_length = 1
                elif len(pause_cmd) == 2:
                    try:
                        pause_length = float(pause_cmd[1])
                    except ValueError:
                        raise ValueError('__PAUSE__ interval in PolledSerialReader must be '
                                         'a float. Found: %s' % cmd)
                else:
                    raise ValueError('Pause format "__PAUSE__ <seconds>"; found %s' % cmd)
                logging.info('Pausing %g seconds', pause_length)
                time.sleep(pause_length)
            else:
                # If it's a normal command we're sending
                logging.info('Sending serial command "%s"', cmd)
                self.serial.write(self._encode_str(cmd, unescape=True))

    ############################
    def read(self):
        try:
            if self.pre_read_cmd:
                self._send_command(self.pre_read_cmd)

            record = super().read()
            return record
        except serial.serialutil.SerialException as e:
            logging.error(str(e))
            return None

    ############################
    def __del__(self):
        if self.stop_cmd:
            try:
                self._send_command(self.stop_cmd)
            except serial.serialutil.SerialException as e:
                logging.error(str(e))
