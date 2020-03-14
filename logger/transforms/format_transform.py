#!/usr/bin/env python3

import sys
from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils import formats
from logger.utils import timestamp
from logger.utils.das_record import DASRecord
from logger.transforms.transform import Transform

################################################################################
class FormatTransform(Transform):
  def __init__(self, format_str, defaults=None):
    """
        format_str    - a format string, as described https://www.w3schools.com/python/ref_string_format.asp
        default_dict - if not None, a dict of field:value pairs specifying the value that
        should be substituted in for any missing fields. If a field:value
        pair is missing from this dict, throw a KeyError.
        """
    
    self.format_str = format_str
    self.defaults = defaults or {}

  def transform(self, record):
    # Make sure record is right format - DASRecord or dict
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
        record_fields = record.fields
    elif type(record) is dict:
        if 'fields' in record:
            record_fields = record['fields']
        else:
            record_fields = record
    else:
        return ('Record passed to FormatTransform was neither a dict nor a '
                'DASRecord. Type was %s: %s' % (type(record), str(record)[:80]))
    
    fields = self.defaults.copy()

    for field, value in record_fields.items():
        fields[field] = value

    # Add the timestamp as a field as well.
    fields['timestamp'] = record.get('timestamp',0)
                            
    try:
        result = self.format_str.format(**fields)

    except KeyError:
        result = None

    if result:
        return result
    return None
