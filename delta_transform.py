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
    # Dict of {field_name: (timestamp, previous_value)} pairs
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
      fields = record.get('timestamp', None)
      
    elif type(record) is list:
      results = []
      for single_record in record:
       results.append(self.transform(single_record))
      return results
    
    else:
      return ('Record passed to DeltaTransform was neither a dict nor a '
              'DASRecord. Type was %s: %s' % (type(record), str(record)[:80])) 
    
    delta_values = {}
    rate_values = {}
    
    for key in fields:
      if last_value.has_key(key):
        delta_values[key] = fields[key] - last_value[key][1]
        rate_values[key] = delta_values[key] / (timestamp - last_value[key][0])
        last_value[key] = [timestamp, fields[key]]
      else:
        delta_values[key] = None
    
    if self.rate is True:
      return DASRecord(timestamp=timestamp, fields=rate_values)
    elif type(self.rate) is list:
      results = {}
      for field in self.rate:
        results[field] = rate_values[field]
      return DASRecord(timestamp=timestamp, fields=results)
    else:
      return DASRecord(timestamp=timestamp, fields=delta_values)
      
     ############################################################################# 
     # OLD CODE
    """
    if type(record) is DASRecord:  
      for single_record in record:
        if not last_value.has_key(single_record.field):
          last_value[single_record.fields] = [timestamp, single_record.value]
          return None
        else:
          fields[single_record.fields] = [single_record.value]

    if type(record) is dict:
      if 'fields' in record:
        for field in record:
          if not last_value.has_key(field):
            last_value[field] = [timestamp, field.value]
            return None
          else:
            fields[field] = [field.value]
      else:
        if not last_value.has_key(record.field):
          last_value[record.field] = [timestamp, record.value]
          return None
        else:
          fields[record.field] = [record.value]
    else:
      return ('Record passed to DeltaTransform was neither a dict nor a '
              'DASRecord. Type was %s: %s' % (type(record), str(record)[:80])) 
    
    for key in fields:
      delta_value = fields[key] - last_value[key][1]
      delta_time = timestamp - last_value[key][0]
      if self.rate is True:
        # return delta_value[key] / delta_time
      else:
        # return delta_value
    
