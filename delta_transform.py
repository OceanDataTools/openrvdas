import logging
import sys

from logger.utils import formats
from logger.utils.das_record import DASRecord
from logger.transforms.transform import Transform

################################################################################

class DeltaTransform:
  def __init__(self, rate=False, field_type=None, last_value=None):
    """
      rate — whether to return the rate (delta/second) for some or all fields, or just return the delta 
      field_type — specifies special field types, if any
    """
    self.rate = rate
    self.field_type = field_type
    # Dict of {field_name: (previous_timestamp, previous_value)} pairs
    self.last_value = {}
    
  ############################
  def transform(self, record):

    if not record:
      return None
    
    fields = {}

    if type(record) is DASRecord:
      fields = record.fields
      timestamp = record.timestamp 
      
    elif type(record) is dict:
      fields = record.get('fields', None)
      timestamp = record.get('timestamp', None)
      
    elif type(record) is list:
      results = []
      for single_record in record:
       results.append(self.transform(single_record))
      return results
    
    else:
      return ('Record passed to DeltaTransform was neither a dict nor a '
              'DASRecord. Type was %s: %s' % (type(record), str(record)[:80])) 
    
    if fields is None or timestamp is None
      return ('Record passed to DeltaTransform either does not have a field or '
              'a timestamp')
    
    delta_values = {}
    rate_values = {}
    
    for key in fields:
      value = fields[key]
      last_timestamp, last_value = self.last_value.get(key, (None, None))
      
      if last_value is not None:
        delta_values[key] = value - last_value
        rate_values[key] = delta_values[key] / (timestamp - last_timestamp)
        
      self.last_value[key] = (timestamp, value)
    
    if self.rate is True:
      return DASRecord(timestamp=timestamp, fields=rate_values)
    elif type(self.rate) is list:
      results = {}
      for field in self.rate:
        results[field] = rate_values[field]
      return DASRecord(timestamp=timestamp, fields=results)
    else:
      return DASRecord(timestamp=timestamp, fields=delta_values)
