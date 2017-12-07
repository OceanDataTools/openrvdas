#!/usr/bin/env python3

import glob
import logging
import sys
import time

sys.path.append('.')

from logger.readers.reader import StorageReader
from logger.utils.formats import Text

################################################################################
# Open and read single-line records from one or more text files.
class TextFileReader(StorageReader):
  """Read lines from one or more text files. Sequentially open all
  files that match the file_spec.
  """
  ############################
  def __init__(self, file_spec=None, tail=False, refresh_file_spec=False,
               retry_interval=0.1, interval=0):
    """
    file_spec    Possibly wildcarded string speficying files to be opened.
                 Special case: if file_spec is None, read from stdin.

    tail         If False, return None upon reaching end of last file; if
                 True, block upon reaching EOF of last file and wait for
                 more records.

    refresh_file_spec
                 If True, refresh the search for matching filenames when
                 reaching last EOF to see if any new matching files have
                 appeared in the interim.

    retry_interval
                 If tail and/or refresh_file_spec are True, how long to
                 wait before looking to see if any new records or files
                 have shown up.

    interval
                 How long to sleep between returning records. In general
                 this should be zero except for debugging purposes.

    Note that the order in which files are opened will probably be in
    alphanumeric by filename, but this is not strictly enforced and
    depends on how glob returns them.
    """

    super().__init__(output_format=Text)

    self.file_spec = file_spec
    self.tail = tail
    self.refresh_file_spec = refresh_file_spec
    self.retry_interval = retry_interval
    self.interval = interval

    # If interval != 0, we need to keep track of our last_read to know
    # how long to sleep
    self.last_read = 0
    
    # Special case if file_spec is None
    if file_spec is None:
      self.current_file = sys.stdin
      return

    # Which files will we use, which haven't we used yet?
    self.unused_file_list = sorted(glob.glob(file_spec))
    if not self.unused_file_list:
      logging.warning('TextFileReader: file_spec "%s" matches no files',
                      file_spec)
    self.used_file_list = []

    # The file we're currently using
    self.current_file = None

  ############################
  def _get_next_file(self):
    """Internal - Open and assign the next unused file to
    self.current_file if we can find one. Return None (and don't mess
    with current_file) if we can't find a next one.
    """
    # If no more unused files, but refresh_file_spec is specified, see
    # if more files have shown up
    if not self.unused_file_list and self.refresh_file_spec:
      matching_files = sorted(glob.glob(self.file_spec))
      self.unused_file_list = [f for f in matching_files
                               if not f in self.used_file_list]
      logging.info('TextFileReader found %d new files matching spec "%s": %s',
                   len(self.unused_file_list), self.file_spec,
                   self.unused_file_list)

    # Are there any more files? If so, get the next one and open it
    if self.unused_file_list:
      next_filename = self.unused_file_list.pop(0)
      logging.info('TextFileReader opening next file "%s"', next_filename)
      self.current_file = open(next_filename, 'r')
      self.used_file_list.append(next_filename)
      return self.current_file

    # If here, we've found no unused next file. Give up
    return None
    
  ############################
  def read(self):
    """Get the next line of text. Return None if there are no more
    records.  To test EOF you'll need to test

      if record is None:
        no more records...

    rather than simply

      if not record:
        could be EOF or simply an empty next line
    """
    if self.interval:
      now = time.time()
      sleep_time = max(0, self.interval - (now - self.last_read))
      logging.debug('Sleeping %f seconds', sleep_time)
      if sleep_time:
        time.sleep(sleep_time)
      
    record = None
    while not record:
      # If we've got a current file, or if _get_next_file() gets one
      # for us, try to read a record.
      if self.current_file or self._get_next_file():
        record = self.current_file.readline()
        if record:
          self.last_read = time.time()
          record = record.rstrip('\n')
          logging.debug('TextFileReader got record "%s"', record)
          return record

        # No record: our current_file has reached EOF. See if more
        # files we should try to read.
        if self._get_next_file():
          # Found a new file to read - loop again right away
          continue

      # No record, no new files, no tail or refresh directive -
      # there's nothing left for us to try. Go home empty-handed.
      if not self.refresh_file_spec and not self.tail:
        return None

      # User wants refresh or tail, so sleep and try again.
      logging.debug('TextFileReader - tail/refresh specified, so sleeping '
                    '%f seconds before trying again', self.retry_interval)
      time.sleep(self.retry_interval)
