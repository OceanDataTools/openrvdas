import logging
import sys

from logger.utils import formats
from logger.utils.das_record import DASRecord
from logger.utils import timestamp
from logger.transforms.transform import Transform

################################################################################

class DeltaTransform:

  # Dict of {field_name: (previous_timestamp, previous_value)} pairs
  last_value_dict = {}

  def polar_diff(self, last_value, value):
    return ((value - last_value) + 180) % 360 - 180

  def __init__(self, rate=False, field_type=None):
  """
    rate — whether to return the rate (delta/second) for some or all fields, or just return the delta
    field_type — if not None, should be a dict specifying special field types, if any
  """
      
    self.rate = rate
    self.field_type = field_type
  
  ############################
  def transform(self, record):
    
    if not record:
      return None
    
    fields = {}

    if type(record) is DASRecord:
      fields = record.fields
      timestamp = record.timestamp 
    
    elif type(record) is dict:
      fields = record['fields']
      timestamp = record['timestamp']
          
      #elif type(record) is dict:
      #fields = record.get('fields', None)
      #timestamp = record.get('timestamp', None)
      
    elif type(record) is list:
      results = []
      for single_record in record:
       results.append(self.transform(single_record))
      return results
    
    else:
      return ('Record passed to DeltaTransform was neither a dict nor a '
              'DASRecord. Type was %s: %s' % (type(record), str(record)[:80])) 
    
    if fields is None or timestamp is None:
      return ('Record passed to DeltaTransform either does not have a field or '
              'a timestamp')
    
    delta_values = {}
    rate_values = {}
    
    for key, value in fields.items():
        
      if key in DeltaTransform.last_value_dict:
          
        last_timestamp, last_value = DeltaTransform.last_value_dict.get(key, (None, None))
            
        if self.field_type is None:
          delta_values[key] = value - last_value
        elif type(self.field_type) is dict:
          if key in self.field_type:
            if self.field_type[key] == 'polar':
              delta_values[key] = DeltaTransform.polar_diff(self, last_value, value)
          else:
            delta_values[key] = value - last_value
        else:
          return ('field_type passed to DeltaTransform is neither None nor a dict')

        rate_values[key] = delta_values[key] / (timestamp - last_timestamp)

        DeltaTransform.last_value_dict[key] = (timestamp, value)

      else:
        DeltaTransform.last_value_dict[key] = (timestamp, value)
        delta_values[key] = None

    if self.rate:
      return DASRecord(timestamp=timestamp, fields=rate_values)
    elif type(self.rate) is list:
      results = {}
      for field in self.rate:
        results[field] = rate_values[field]
      return DASRecord(timestamp=timestamp, fields=results)
    else:

      return DASRecord(timestamp=timestamp, fields=delta_values)
