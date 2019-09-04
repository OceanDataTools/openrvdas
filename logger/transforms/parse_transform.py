#!/usr/bin/env python3

import sys
from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils import formats
from logger.utils import record_parser

from logger.transforms.transform import Transform

################################################################################
class ParseTransform(Transform):
  """Parse a "<data_id> <timestamp> <message>" record and return
  corresponding dict of values (or JSON or DASRecord if specified)."""
  def __init__(self, definition_path=record_parser.DEFAULT_DEFINITION_PATH,
               return_json=False, return_das_record=False):
               
    """
    ```
    definition_path
            Wildcarded path matching YAML definitions for devices.

    return_json
            Return a JSON-encoded representation of the dict
            instead of a dict itself.

    return_das_record
            Return a DASRecord object.
    ```
    """
    self.parser = record_parser.RecordParser(
      definition_path=definition_path,
      return_json=return_json,
      return_das_record=return_das_record)

  ############################
  def transform(self, record):
    """Parse record and return DASRecord."""
    if record is None:
      return None
    return self.parser.parse_record(record)
