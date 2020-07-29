import logging
import sys

from logger.utils import formats
from logger.utils.das_record import DASRecord
from logger.transforms.transform import Transform

################################################################################

class DeltaTransform:

  def __init__(self, rate=False, field_type=None, last_value=None):
    self.rate = rate
    self.field_type = field_type
    # Dict of {field_name: (timestamp, previous_value)} pairs
    self.last_value = {}
    
  ############################
  def transform(self, record):

    if not record:
      return None
    
    timestamp = record.timestamp
    current_value = {}

    if type(record) is DASRecord:
      for single_record in record:
        if not last_value.has_key(single_record.field):
          last_value[single_record.fields] = [timestamp, single_record.value]
          return None
        else:
          current_value[single_record.fields] = [single_record.value]

    if type(record) is dict:
      if 'fields' in record:
        for field in record:
          if not last_value.has_key(field):
            last_value[field] = [timestamp, field.value]
            return None
          else:
            current_value[field] = [field.value]
      else:
        if not last_value.has_key(record.field):
          last_value[record.field] = [timestamp, record.value]
          return None
        else:
          current_value[record.field] = [record.value]
    else:
      return ('Record passed to DeltaTransform was neither a dict nor a '
              'DASRecord. Type was %s: %s' % (type(record), str(record)[:80])) 
    
    for key in current_value:
      delta_value = current_value[key] - last_value[key][1]
      delta_time = timestamp - last_value[key][0]
      if self.rate is True:
        # return delta_value[key] / delta_time
      else:
        # return delta_value
    
