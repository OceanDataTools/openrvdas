#!/usr/bin/env python3

import logging
import logging.handlers
import time

from os import makedirs
from os.path import dirname

# Default base of logging path. See setUpStdErrLogging() for explanation.
DEFAULT_STDERR_PATH = '/var/log/openrvdas/'
DEFAULT_LOGGING_FORMAT = '%(asctime)-15s.%(msecs)03dZ %(filename)s:%(lineno)d: %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S'  # ISO8601

################################################################################
# Set up logging first of all
def setUpStdErrLogging(stderr_file=None, stderr_path=None,
                       logging_format=DEFAULT_LOGGING_FORMAT, log_level=None):
  """Set up default logging module handler to send stderr to console but
  also, if specified, to a stderr_file. If the string stderr_file is a
  fully-qualified path (i.e. starts with '/'), use that; if not append
  it to the string stderr_path.
  """
  #logging.debug('setUpStdErrLogging file %s, path %s, level %s',
  #              stderr_file, stderr_path, log_level)
  
  logging.basicConfig(format=logging_format)
  if log_level:
    logging.root.setLevel(log_level)

  # If they've not given us a file to log to, nothing else to do
  if not stderr_file:
    return
  
  # Send output to stderr
  formatter = logging.Formatter(fmt=logging_format,
                                datefmt=DEFAULT_DATE_FORMAT)
  console_handler = logging.StreamHandler()
  console_handler.setFormatter(formatter)
  handlers = [console_handler]

  # If not a full path, use default base path
  if not stderr_file.find('/') == 0:
    stderr_path = stderr_path or DEFAULT_STDERR_PATH
    stderr_file = stderr_path + stderr_file

  # Try to make enclosing dir if it doesn't exist
  makedirs(dirname(stderr_file), exist_ok=True)

  # Attach a filehandler that will write to the specified file
  file_handler = logging.handlers.WatchedFileHandler(stderr_file)
  file_handler.setFormatter(formatter)

  logging.root.handlers = [console_handler, file_handler]
  if log_level:
    logging.root.setLevel(log_level)

############################
class StdErrLoggingHandler(logging.Handler):
  """Write Python logging.* messages to whatever writer we're passed. To
  use, run

    logging.getLogger().addHandler(StdErrLoggingHandler(my_writer))
  """
  def __init__(self, writers, logging_format=DEFAULT_LOGGING_FORMAT):
    super().__init__()
    self.writers = writers

    self.formatter = logging.Formatter(fmt=logging_format,
                                       datefmt=DEFAULT_DATE_FORMAT)
    self.formatter.converter = time.gmtime

  def emit(self, record):
    # Temporarily push the logging level up as high as it can go to
    # effectively disable recursion induced by logging that occurs inside
    # whatever writer we're using.
    log_level = logging.root.getEffectiveLevel()
    logging.root.setLevel(logging.CRITICAL)

    message = self.formatter.format(record)
      
    if type(self.writers) is list:
      [writer.write(message) for writer in self.writers]
    else:
      self.writers.write(message)
    logging.root.setLevel(log_level)
