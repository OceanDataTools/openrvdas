#!/usr/bin/env python3

import sys
sys.path.append('.')

from logger.utils import formats
from logger.utils import nmea_parser

from logger.transforms.transform import Transform

################################################################################
class ParseNMEATransform(Transform):
  """Parse a "<data_id> <timestamp> <nmea>" record and return
  corresponding DASRecord."""
  def __init__(self, json=False,
               message_path=nmea_parser.DEFAULT_MESSAGE_PATH,
               sensor_path=nmea_parser.DEFAULT_SENSOR_PATH,
               sensor_model_path=nmea_parser.DEFAULT_SENSOR_MODEL_PATH,
               time_format=None):
    """
    json    Return a JSON-encoded representation of the DASRecord instead
            of DASRecord itself.

    message_path, sensor_path, sensor_model_path
            Wildcarded path matching JSON definitions for sensor messages,
            sensors and sensor models.
    """
    super().__init__(input_format=formats.NMEA,
                     output_format=formats.Python_Record)
    self.json = json
    self.parser = nmea_parser.NMEAParser(message_path, sensor_path,
                                         sensor_model_path,
                                         time_format=time_format)

  ############################
  def transform(self, record):
    """Parse record and return DASRecord."""
    if record is None:
      return None
    result = self.parser.parse_record(record)
    if not result:
      return None
    if self.json:
      return result.as_json()
    return result
