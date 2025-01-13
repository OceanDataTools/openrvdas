#!/usr/bin/env python3

import logging
import sys
import time
from itertools import cycle

# Don't freak out if pyserial isn't installed - unless they actually
# try to instantiate a SerialReader
try:
    import serial
    SERIAL_MODULE_FOUND = True
except ModuleNotFoundError:
    SERIAL_MODULE_FOUND = False

sys.path.append('.')
from logger.readers.serial_reader import SerialReader  # noqa: E402


############################
def is_string_or_list_of_strings(cmd):
    if isinstance(cmd, str):
        return True
    elif isinstance(cmd, list):
        return all(isinstance(item, str) for item in cmd)
    return False


############################
def is_dict_of_lists_of_strings(cmd):
    if not isinstance(cmd, dict):
        return False

    # So we have a dict. Check that all values are either strings
    # or lists of strings
    for value in cmd.values():
        if isinstance(value, str):
            continue
        elif (isinstance(value, list) and
              all(isinstance(item, str) for item in value)):
            continue
        else:
            return False

    # If got this far, it all checks out
    return True

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

        Notable arguments:

        start_cmd
            If not None, may be string or list of strings. If a single string,
            it is sent to the serial port as soon as it is opened. If a list of
            strings, each string in the list is sent in sequence.

        stop_cmd
            Much as start_cmd, but is sent when the PolledSerialReader is closed
            or destroyed.

        pre_read_cmd
            Much as start_cmd and stop_cmd, except the string or list of strings
            are sent each time the PolledSerialReader's read() method is called,
            prior to trying to read from the port.

            In addition to a string or list of strings, pre_read_cmd may be a *dict*
            of lists of strings:

                pre_read_cmd:
                  key1: ['command 1_1', 'command 1_2]
                  key2: ['command 2_1', 'command 2_2]
                  key3: ...
                ...
            The first time read() is called, the strings associated with key1 will be
            sent. The second time, those associated with key2, and so on. When the end
            of the dict is reached, it will start again with key1.

        For all of these arguments, a special string, ``__PAUSE__``, is recognized. If
        followed by a number (e.g. ``__PAUSE__ 5``), it will be interpreted as a command
        to pause for that many seconds prior to sending the next command. If no number
        is given, it will pause for one second.
        """
        self.start_cmd = start_cmd
        self.pre_read_cmd = pre_read_cmd
        self.stop_cmd = stop_cmd

        # Type check our pre_read commands
        if start_cmd and not is_string_or_list_of_strings(start_cmd):
            raise ValueError('PolledSerialReader start_cmd must either be None, '
                             f'a string, or a list of strings. Found: {start_cmd}')
        if stop_cmd and not is_string_or_list_of_strings(stop_cmd):
            raise ValueError('PolledSerialReader stop_cmd must either be None, '
                             f'a string, or a list of strings. Found: {stop_cmd}')
        if pre_read_cmd and not (is_string_or_list_of_strings(pre_read_cmd) or
                                 is_dict_of_lists_of_strings(pre_read_cmd)):
            raise ValueError('PolledSerialReader pre_read_cmd must either be None, '
                             'a string, or a list of strings, or a dict of lists of '
                             f'strings. Found: {pre_read_cmd}')

        if isinstance(pre_read_cmd, dict):
            self.command_cycle = cycle(pre_read_cmd.items())

        super().__init__(port=port, baudrate=baudrate, bytesize=bytesize,
                         parity=parity, stopbits=stopbits, timeout=timeout,
                         xonxoff=xonxoff, rtscts=rtscts, write_timeout=write_timeout,
                         dsrdtr=dsrdtr, inter_byte_timeout=inter_byte_timeout,
                         exclusive=exclusive, max_bytes=max_bytes, eol=eol,
                         encoding=encoding, encoding_errors=encoding_errors)
        if not SERIAL_MODULE_FOUND:
            raise RuntimeError('Serial port functionality not available. Please '
                               'install Python module pyserial.')
        if self.start_cmd:
            try:
                if isinstance(self.start_cmd, list):  # list of commands
                    for cmd in self.start_cmd:
                        self._send_command(cmd)
                else:
                    self._send_command(start_cmd)
            except serial.serialutil.SerialException as e:
                logging.error(str(e))

    ############################
    def _send_command(self, cmd):
        """Check if command is a 'pause'; if so, sleep, otherwise send it to serial port."""
        logging.debug(f'Sending {cmd}')
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
            #self.serial.write(self._encode_str(cmd))
            self.serial.flush()

        logging.debug(f'Done sending {cmd}')

    ############################
    def read(self):
        try:
            # Do we need to send anything prior to reading?
            if not self.pre_read_cmd:  # no pre_read_cmd
                pass
            elif isinstance(self.pre_read_cmd, list):  # list of commands
                for cmd in self.pre_read_cmd:
                    self._send_command(cmd)
            elif isinstance(self.pre_read_cmd, dict):  # dict of lists of commands
                key, commands = next(self.command_cycle)
                for cmd in commands:
                    self._send_command(cmd)
            elif self.pre_read_cmd:   # simple string command
                self._send_command(self.pre_read_cmd)

            logging.debug(f'read() is being called')
            record = super().read()
            logging.debug(f'Returned from read() with: {record}')
            return record
        except serial.serialutil.SerialException as e:
            logging.error(str(e))
            return None

    ############################
    def __del__(self):
        if self.stop_cmd:
            try:
                if isinstance(self.stop_cmd, list):  # list of commands
                    for cmd in self.stop_cmd:
                        self._send_command(cmd)
                else:
                    self._send_command(self.stop_cmd)
            except serial.serialutil.SerialException as e:
                logging.error(str(e))
