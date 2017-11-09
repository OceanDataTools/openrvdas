#!/usr/bin/env python3

"""DASRecord is a structured representation of the field names and
values (and metadata) contained in a sensor record.

If a json string is passed, it is parsed into a dictionary and its
values for timestamp, fields and metadata are copied in. Otherwise,
the DASRecord object is initialized with the passed-in values for
instrument, timestamp, fields (a dictionary of fieldname-value pairs)
and metadata.

If timestamp is not specified, the instance will use the current time.
"""

import json

from logger.utils import timestamp as ts
from utils.read_json import parse_json

################################################################################
class DASRecord:
  ############################
  def __init__(self, json=None, instrument=None, timestamp=None,
               fields={}, metadata={}):
    if json:
      parsed = parse_json(json)
      self.instrument = parsed.get('instrument', None)
      self.timestamp = parsed.get('timestamp', None)
      self.fields = parsed.get('fields', {})
      self.metadata = parsed.get('metadata', {})
    else:
      #self.source = 
      self.instrument = instrument
      self.timestamp = ts.timestamp()
      self.fields = fields
      self.metadata = metadata

  ############################
  def as_json(self):
    json_dict = {
      'instrument': self.instrument,
      'timestamp': self.timestamp,
      'fields': self.fields,
      'metadata': self.metadata
    }
    return json.dumps(json_dict)
