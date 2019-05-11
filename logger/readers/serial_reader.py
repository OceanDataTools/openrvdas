#!/usr/bin/env python3

import logging
import socket
import sys
import time

# Don't freak out if pyserial isn't installed - unless they actually
# try to instantiate a SerialReader
try:
  import serial
  SERIAL_MODULE_FOUND = True
except ModuleNotFoundError:
  SERIAL_MODULE_FOUND = False

sys.path.append('.')

from logger.utils.formats import Text
from logger.readers.reader import Reader

################################################################################
class SerialReader(Reader):
  """
  Read text records from a serial port.
  """
  def __init__(self,  port, baudrate=9600, bytesize=8, parity='N',
               stopbits=1, timeout=None, xonxoff=False, rtscts=False,
               write_timeout=None, dsrdtr=False, inter_byte_timeout=None,
               exclusive=None, max_bytes=None, lf=None):
    """
    If max_bytes is specified on initialization, read up to that many
    bytes when read() is called. If not specified, read() will read up to
    the first newline it receives. In both cases, if timeout is specified,
    it will return after timeout with as many bytes as it has succeeded in
    reading.
    """
    super().__init__(output_format=Text)

    if not SERIAL_MODULE_FOUND:
      raise RuntimeError('Serial port functionality not available. Please '
                         'install Python module pyserial.')

    self.serial = serial.Serial(port=port, baudrate=baudrate, bytesize=bytesize,
                                parity=parity, stopbits=stopbits,
                                timeout=timeout, xonxoff=xonxoff, rtscts=rtscts,
                                write_timeout=write_timeout, dsrdtr=dsrdtr,
                                inter_byte_timeout=inter_byte_timeout,
                                exclusive=exclusive)
    self.max_bytes = max_bytes
    self.lf = lf

  ############################
  def read(self):
    try:
      if self.lf:
        record = self.serial.read_until(self.lf, self.max_bytes)
      elif self.max_bytes:
        record = self.serial.read(self.max_bytes)
      else:
        record = self.serial.readline()
      if not record:
        return None
      return record.decode('utf-8').rstrip()
    except serial.serialutil.SerialException as e:
      logging.error(str(e))
      return None
