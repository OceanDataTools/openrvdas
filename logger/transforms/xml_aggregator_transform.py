#!/usr/bin/env python3
"""Aggregate passed lines of XML until a complete XML record has been
seen, then pass it on as a single record. Relies on the simplistic
heuristic of expecting each new record to begin with '<?xml...', which
means that we won't recognize the end of a record until we see the
beginning of the next one.

TODO: Replace by something using xml.sax.xmlreader.IncrementalParser,
with a custom ContentHandler that remembers the first opening tag we
see at the start of a record and triggers parsing when is sees the
corresponding closing tag.

"""

import logging
import sys
import threading

sys.path.append('.')

from logger.utils import formats

from logger.transforms.transform import Transform

################################################################################
class XMLAggregatorTransform(Transform):
  ############################
  def __init__(self, delimiter='<?xml'):
    super().__init__(input_format=formats.Text, output_format=formats.XML)
    self.delimiter = delimiter

    # Only let one thread touch buffer at a time. Of course, if we're
    # getting interleaved lines from different XML records here, we're
    # screwed anyway.
    self.buffer_lock = threading.Lock()
    self.buffer = ''

  ############################
  def transform(self, record):
    if record is None:
      return None
    
    logging.debug('XMLAggregatorTransform.read() got record: %s', record)  
    with self.buffer_lock:
      if record.find(self.delimiter) > -1:
        logging.debug('XMLAggregatorTransform.read() got new record delimiter')
        completed_record = self.buffer
        self.buffer = record
        return completed_record
      else:
        self.buffer += record + '\n'
        return None
