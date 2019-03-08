#!/usr/bin/env python3

import logging
import logging.handlers

from os import makedirs
from os.path import dirname

# Default base of logging path. See setUpStdErrLogging() for explanation.
DEFAULT_STDERR_PATH = '/var/log/openrvdas/'
LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d: %(message)s'

################################################################################
# Set up logging first of all
def setUpStdErrLogging(stderr_file=None, stderr_path=None, log_level=None):
  """Set up default logging module handler to send stderr to console but
  also, if specified, to a stderr_file. If the string stderr_file is a
  fully-qualified path (i.e. starts with '/'), use that; if not append
  it to the string stderr_path.
  """
  logging.info('setUpStdErrLogging file %s, path %s, level %s',
               stderr_file, stderr_path, log_level)
  
  logging.basicConfig(format=LOGGING_FORMAT)
  if log_level:
    logging.root.setLevel(log_level)

  # If they've not given us a file to log to, nothing else to do
  if not stderr_file:
    return
  
  # Send output to stderr
  formatter = logging.Formatter(fmt=LOGGING_FORMAT)
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
