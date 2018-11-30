#!/usr/bin/env python3

import json
import logging
import sys

sys.path.append('.')

from logger.utils import formats
from logger.utils.das_record import DASRecord
from logger.transforms.transform import Transform

################################################################################
#
class FromJSONTransform(Transform):
  """Convert passed JSON to either a DASRecord or a dict.
  """
  def __init__(self, das_record=False):
    """Parse the received JSON and convert to appropriate data
    structure. If das_record == True, assume we've been passed a dict
    of field:value pairs, and try to embed them into a DASRecord.
    """
    super().__init__(input_format=formats.Python_Record,
                     output_format=formats.Text)

    self.das_record = das_record

  ############################
  def transform(self, record):
    """Parse JSON record to Python data struct or DASRecord."""
    if not record:
      return None

    if not type(record) is str:
      logging.warning('FromJSON transform received non-string input, '
                      'type: "%s"', type(record))
      return None
    
    try:
      data = json.loads(record)
    except:
      logging.warning('Failed to parse JSON string: "%s"', record)
      return None

    if not self.das_record:
      return data

    if not type(data) is dict:
      logging.warning('FromJSON asked to create DASRecord from non-dict '
                      'data: "%s"', type(data))
      return None
    
    return DASRecord(fields=data)
