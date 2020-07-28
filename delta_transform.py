import logging
import sys

from logger.utils import formats
from logger.utils.das_record import DASRecord
from logger.transforms.transform import Transform

################################################################################

class DeltaTransform:

  def __init__(self, rate=False, field_type=None):
    self.rate = rate
    self.field_type = field_type
  
  ############################
  def transform(self, record):

    if not record:
      return None
               
    fields = {}

    if type(record) is DASRecord:
      results = []
      for single_record in record:
        if not fields.has_key(single_record.field):
          fields[single_record.fields] = [single_record.timestamp, single_record.value]
          return None
        else:
          delta_value = single_record.value - fields[single_record.field][1]
          delta_time = single_record.timestamp - fields[single_record.field][0]
          fields[single_record.fields] = [single_record.timestamp, single_record.value]

        results.append(self.transform(single_record))

    if type(record) is dict:
      results = []
      if 'fields' in record:
        for field in record:
          if not fields.has_key(field):
            fields[field] = [field.timestamp, field.value]
            return None
          else:
            delta_value = field.value - fields[field][1]
            delta_time = field.timestamp - fields[field][0]
            fields[field] = [field.timestamp, field.value]
      else:
        if not fields.has_key(record.field):
          fields[record.field] = [record.timestamp, record.value]
          return None
        else:
          delta_value = record.value - fields[field][1]
          delta_time = record.timestamp - fields[field][0]
          fields[record.field] = [record.timestamp, record.value]
    else:
      return ('Record passed to DeltaTransform was neither a dict nor a '
              'DASRecord. Type was %s: %s' % (type(record), str(record)[:80])) 


    if self.rate is True:
      return delta_value / delta_time
    else:
      return delta_value

    """ (OLD) TAKEN FROM QC_FILTER_TRANSFORM W/ SLIGHT MODIFICATIONS:
    if not record:
      return None

    # If we've got a list, hope it's a list of records. Recurse,
    # calling transform() on each of the list elements in order and
    # return the resulting list.
    if type(record) is list:
      results = []
      for single_record in record:
       results.append(self.transform(single_record))
      return results

    if type(record) is DASRecord:
      fields = record.fields
      timestamp = record.timestamp
    elif type(record) is dict:
      if 'fields' in record:
        fields = record['fields']
      else:
        fields = record

      if 'timestamp' in record:
        timestamp = record['timestamp']
      else:
        timestamp = record
    else:
      return ('Record passed to DeltaTransform was neither a dict nor a '
              'DASRecord. Type was %s: %s' % (type(record), str(record)[:80]))
    """
