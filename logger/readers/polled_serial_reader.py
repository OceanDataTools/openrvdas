#!/usr/bin/env python3

import logging
import sys

sys.path.append('.')

from logger.readers.serial_reader import SerialReader

################################################################################
class PolledSerialReader(SerialReader):
  """
  Read text records from a serial port.
  """
  def __init__(self,  port, baudrate=9600, bytesize=8, parity='N',
               stopbits=1, timeout=None, xonxoff=False, rtscts=False,
               write_timeout=None, dsrdtr=False, inter_byte_timeout=None,
               exclusive=None, max_bytes=None, lf=None, start_cmd=None,
               pre_read_cmd=None, stop_cmd=None):
    """
    Extends the standard serial reader by allowing the user to define
    strings to send to the serial host on startup, before each read and 
    just prior to the reader being destroyed
    """
    super().__init__(port=port, baudrate=baudrate, bytesize=bytesize,
                     parity=parity, stopbits=stopbits, timeout=timeout,
                     xonxoff=xonxoff, rtscts=rtscts, write_timeout=write_timeout,
                     dsrdtr=dsrdtr, inter_byte_timeout=inter_byte_timeout,
                     exclusive=exclusive)

    self.start_cmd = start_cmd
    self.pre_read_cmd = pre_read_cmd
    self.stop_cmd = stop_cmd

    if(self.start_cmd):
      try:
        self.serial.write(self.start_cmd.encode('utf-8'))
      except serial.serialutil.SerialException as e:
        logging.error(str(e))

  ############################
  def read(self):
    try:
      if self.pre_read_cmd:
        self.serial.write(self.pre_read_cmd.encode('utf-8'))

      record = self.read()
      return record
    except serial.serialutil.SerialException as e:
      logging.error(str(e))
      return None

  ############################
  def __del__(self):
    if(self.stop_cmd):
      try:
        self.serial.write(self.stop_cmd.encode('utf-8'))
      except serial.serialutil.SerialException as e:
        logging.error(str(e))
