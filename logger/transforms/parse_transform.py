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
               return_json=False, return_das_record=False,
               metadata_interval=None):
    """
    ```
    definition_path
            Wildcarded path matching YAML definitions for devices.

    return_json
            Return a JSON-encoded representation of the dict
            instead of a dict itself.

    return_das_record
            Return a DASRecord object.

    metadata_interval
            If not None, include the description, units and other metadata
            pertaining to each field in the returned record if those data
            haven't been returned in the last metadata_interval seconds.
    ```
    """
    self.parser = record_parser.RecordParser(
      definition_path=definition_path,
      return_json=return_json,
      return_das_record=return_das_record,
      metadata_interval=metadata_interval)

  ############################
  def transform(self, record):
    """Parse record and return DASRecord."""
    if record is None:
      return None
    return self.parser.parse_record(record)
