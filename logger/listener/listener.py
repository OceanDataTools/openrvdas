#!/usr/bin/env python3

import logging
import logging.handlers
import sys
import time

from os import makedirs
from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.readers.composed_reader import ComposedReader
from logger.writers.composed_writer import ComposedWriter
from logger.utils.stderr_logging import setUpStdErrLogging
    
################################################################################
class Listener:
  """Listener is a simple, yet relatively self-contained class that
  takes a list of one or more Readers, a list of zero or more
  Transforms, and a list of zero or more Writers. It calls the Readers
  (in parallel) to acquire records, passes those records through the
  Transforms (in series), and sends the resulting records to the Writers
  (in parallel).

  """
  ############################
  def __init__(self, readers, transforms=[], writers=[], host_id='',
               interval=0, name=None, check_format=False,
               stderr_file=None, stderr_path=None, log_level=None):
    """listener = Listener(readers, transforms=[], writers=[],
                        interval=0, check_format=False)

    readers        A single Reader or a list of Readers.

    transforms     A single Transform or a list of zero or more Transforms

    writers        A single Writer or a list of zero or more Writers

    host_id        Optional host_id on which Listener is to be run. Ignored
                   here, but it may show up as part of a config, so we need
                   to be able to handle is in kwargs.

    interval       How long to sleep before reading sequential records

    name           Optional human-readable short name to be used in displays

    check_format   If True, attempt to check that Reader/Transform/Writer
                   formats are compatible, and throw a ValueError if they
                   are not. If check_format is False (the default) the
                   output_format() of the whole reader will be
                   formats.Unknown.

    stderr_file    File to log stderr messages to. Try to create if it
                   does not exist.  If a full path (beginning with
                   '/'), use that. If they only a file name or partial
                   path (anything not beginning with '/'), append the
                   stderr_file name to DEFAULT_STDERR_PATH, defined
                   above.

    Sample use:

    listener = Listener(readers=[NetworkReader(':6221'),
                                 NetworkReader(':6223')],
                        transforms=[TimestampTransform()],
                        writers=[TextFileWriter('/logs/network_recs'),
                                 TextFileWriter(None)],
                        interval=0.2)
    listener.run()

    Calling listener.quit() from another thread will cause the run() loop
    to exit.
    """
    # Set up logging first of all
    setUpStdErrLogging(stderr_file=stderr_file,
                       stderr_path=stderr_path,
                       log_level=log_level)
    
    ###########
    # Create readers, writers, etc.
    self.reader = ComposedReader(readers=readers, check_format=check_format)
    self.writer = ComposedWriter(transforms=transforms, writers=writers,
                                 check_format=check_format)
    self.interval = interval
    self.name = name or 'Unnamed listener'
    self.last_read = 0

    self.quit_signalled = False

  ############################
  def quit(self):
    """
    Signal 'quit' to all the readers.
    """
    self.quit_signalled = True
    logging.debug('Listener.quit() called')

  ############################
  def run(self):
    """
    Read/transform/write until either quit() is called in a separate
    thread, or ComposedReader returns None, indicating that all its
    component readers have returned EOF.
    """
    record = ''
    try:
      while not self.quit_signalled and record is not None:
        record = self.reader.read()
        self.last_read = time.time()
        logging.debug('ComposedReader read: "%s"', record)
        if record:
          self.writer.write(record)

        if self.interval:
          time_to_sleep = self.interval - (time.time() - self.last_read)
          time.sleep(max(time_to_sleep, 0))

    # Exit in an orderly fashion if someone hits Ctl-C
    except KeyboardInterrupt:
      logging.info('Listener %s received KeyboardInterrupt - exiting.',
                   self.name or '')
    except Exception as e:
      logging.error('Listener %s received exception: %s', str(e))
