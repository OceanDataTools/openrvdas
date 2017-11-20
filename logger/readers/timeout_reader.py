#!/usr/bin/env python3
"""Instantiated with a client Reader instance (such as a
NetworkReader), an interval, a timeout and optional message. When its
read() method is called, it iteratively calls its passed reader's
read() method every interval seconds, discarding the received
output. It only returns if/when the client reader fails to return a
record within timeout seconds, in which case it returns either the
passed timeout message or a default one, warning that no records have
been received within the specified timeout.  s (in parallel) and
process their responses through zero or more Transforms (in series).

Instantiation:

  reader = TimeoutReader(reader, timeout, message=None)

    reader         A client reader instance

    timeout        Timeout interval in seconds

    message        Message to be returned if client reader fails to return
                   a record within the timeout interval

    empty_is_okay If True, receiving an empty record is sufficient to reset
                  the timer.
    none_is_okay  If True, receiving a 'None' record is sufficient to reset
                  the timer.
Use:

  record = reader.read()

Sample:

  gyr1_reader = ComposedReader(NetworkReader(':6224'),
                               RegexFilterTransform('^gyr1'))
  reader = TimeoutReader(reader=gyr1_reader,
                         timeout=15,
                         message='No Gyroscope records received for 15 seconds')
"""

import logging
import signal
import sys
import threading
import time

sys.path.append('.')

from logger.readers.reader import Reader
from logger.transforms.transform import Transform
from logger.utils.formats import Text

##############################
# Create a custom exception we can raise when we hit timeout
class ReaderTimeout(StopIteration):
  pass

################################################################################
class TimeoutReader(Reader):
  ############################
  def __init__(self, reader, timeout, message=None,
               empty_is_okay=False, none_is_okay=False):
    super().__init__(output_format=Text)

    self.reader = reader
    self.timeout = timeout
    self.message = message or ('Timeout: no %s record received in %d seconds'
                               % (reader, timeout))
    self.empty_is_okay=empty_is_okay
    self.none_is_okay=none_is_okay

  ############################
  # If timeout fires, raise our custom exception
  def handler(self, signum, frame):
    logging.info('Read operation timed out')
    raise ReaderTimeout

  ############################
  # Start retrieving records from client reader
  def read(self):

    # Set the handler that will provide the needed interrupt, raising
    # the (ever-obscure) StopIterationError if we exceed the timeout.
    # TODO: should we create 
    signal.signal(signal.SIGALRM, self.handler)
    last_read = time.time()
    
    while True:
      signal.alarm(self.timeout)

      try:
        # Loop inside the 'try' until we get a record
        record = None
        while not record:
          record = self.reader.read()
          if self.empty_is_okay:
            break
          if record is None and self.none_is_okay:
            break

        # If here, we've gotten a record - fall through and reset timer
        now = time.time()
        logging.info('TimeoutReader got record after %2.2f seconds: %s',
                     now - last_read, record)
        last_read = now

      # If we haven't gotten a (valid) record within timeout seconds,
      # our handler will fire off a ReaderTimeoutError. Break out of
      # our loop and return our complaint.
      except ReaderTimeout:
        interval = time.time() - last_read
        logging.info('TimeoutReader no records after %2.2f seconds', interval)
        break
        
    # If here, we've failed to get a record within the specified
    # timeout. Disable the timeout alarm and return our
    # complaint/warning.
    signal.alarm(0)
    return self.message

