#!/usr/bin/env python3
"""Parse a "<data_id> <timestamp> <nmea>" record and return
corresponding DASRecord.

"""

import sys
sys.path.append('.')

from logger.utils import formats
from logger.utils import nmea_parser

from logger.transforms.transform import Transform

################################################################################
# If timestamp_format is not specified, use default format
class ParseNMEATransform(Transform):
  def __init__(self, json=False,
               message_path=nmea_parser.DEFAULT_MESSAGE_PATH,
               sensor_path=nmea_parser.DEFAULT_SENSOR_PATH,
               sensor_model_path=nmea_parser.DEFAULT_SENSOR_MODEL_PATH):
    super().__init__(input_format=formats.NMEA,
                     output_format=formats.Python_Record)
    self.json = json
    self.parser = nmea_parser.NMEAParser(message_path, sensor_path,
                                         sensor_model_path)
  
  ############################
  # Parse record and return DASRecord
  def transform(self, record):
    if record is None:
      return None
    result = self.parser.parse_record(record)
    if not result:
      return None
    if self.json:
      return result.as_json()
    return result
