#!/usr/bin/env python3

'''
Original credit: Australian Antarctic Division

This transform is used to prepend the data_id from a DASRecord or Dict to 
the field names in the record and write it to the cache data server.

This transform is used to cache "live" values for each logger before transform are done for use by front-ends

'''

import sys
import logging

from logger.transforms.to_das_record_transform import ToDASRecordTransform
from logger.transforms.to_json_transform import ToJSONTransform 
from logger.transforms.transform import Transform
from logger.utils.das_record import DASRecord
from logger.writers.cached_data_writer import CachedDataWriter
from logger.writers.composed_writer import ComposedWriter

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))


################################################################################
class CacheLogTransform(Transform):
  """Writes current string or DAS record to cache data server"""
  
  def __init__(self, field_name, data_server="localhost:8766"):
    """
    ```
    field_name
        A string key to store these logs against in the cache data server
    ```
    """
    self.field_name = field_name

    to_das_record_transform = ToDASRecordTransform(data_id='output', field_name=field_name)
    cache_writer = CachedDataWriter(data_server=data_server)

    self.cache_writer = ComposedWriter(
        transforms=to_das_record_transform,
        writers=[cache_writer]
      )
    
    self.cache_writer_for_DASRecords = ComposedWriter(
        transforms=[ToJSONTransform(), to_das_record_transform],
        writers=[cache_writer]
      )


  def transform(self, record):
    """Write current string or DAS record to the cache data server"""
    # If we've got a list, hope it's a list of records. Recurse,
    # calling transform() on each of the list elements in order and
    # return the resulting list.
    try:
      if type(record) is list:
        results = []
        for single_record in record:
          results.append(self.transform(single_record))
        return results
      elif type(record) is DASRecord:
        self.cache_writer_for_DASRecords.write(record)
      else:
        # Same logic, but with dicts instead of a DASRecord
        self.cache_writer_for_DASRecords.write(record)
    except Exception as e:
      logging.error(e)
      
    return record