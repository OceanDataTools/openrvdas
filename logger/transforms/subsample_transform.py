#!/usr/bin/env python3
"""Compute subsamples of input data.
"""

import logging
import sys
import time

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord
from logger.utils.subsample import subsample
from logger.transforms.derived_data_transform import DerivedDataTransform

################################################################################
class SubsampleTransform(DerivedDataTransform):
  """Transform that computes subsamples of the specified variables.
  """
  def __init__(self, field_spec, back_seconds=60*60):
    """
    ```
    field_spec - a dict that contains the fields to be subsampled,
                 the algorithms and parameters to be used, and the
                 names of the output values to be produced.

      e.g.  {
              field_1:{
                output: smoothed_field_1,
                subsample:{
                  'type':'boxcar_average', 'window': 30, 'interval': 30
                }
              },
              field_2:{
                output: smoothed_field_2,
                subsample:{
                  'type':'boxcar_average', 'window': 15, 'interval': 5
                }
              }
            }

    back_seconds - the number of seconds of data to cache for use by sampler

    ```
    """
    super().__init__()

    self.field_spec = field_spec
    self.back_seconds = back_seconds
    self.field_list = list(field_spec.keys())

    # A dict of the cached values we're hanging onto
    self.cached_values = {f:[] for f in self.field_list}

    # Last timestamp that's been emitted for each field
    self.last_timestamp = {f:0 for f in self.field_list}

  ############################
  def fields(self):
    """Which fields are we interested in to produce transformed data?"""
    return self.field_list

  ############################
  def _add_record(self, record):
    """Cached the values contained in a new record."""
    if type(record) not in [DASRecord, dict]:
      logging.error('SubsampleTransform records must be dict or '
                    'DASRecord. Received type %s: %s', type(record), record)
      return

    if type(record) is DASRecord:
      timestamp = record.timestamp
      fields = record.fields
    else:
      timestamp = record.get('timestamp', None)
      fields = record.get('fields', None)

    if not fields:
      logging.error('SubsampleTransform: no fields found in record: %s', record)
      return

    # First, copy the new data into our cache
    for field in self.field_list:
      new_vals = fields.get(field, None)
      if not new_vals:
        continue
      # If list, we assume it's [(ts, value), (ts, value),...]
      if type(new_vals) is list:
        self.cached_values[field].extend(new_vals)
        # If not list, assume DASRecord or simple field dict; add tuple
      elif timestamp:
        self.cached_values[field].append((timestamp, new_vals))
      else:
        logging.error('SubsampleTransform found no timestamp in '
                      'record: %s', record)

  ############################
  def _clean_cache(self):
    """Which fields are we interested in to produce transformed data?"""
    now = time.time()
    for field in self.field_list:
      # Iterate forward through field cache until we find a timestamp
      # that is recent enough to keep
      cache = self.cached_values[field]
      for keep_index in range(len(cache)):
        if cache[keep_index][0] > now - self.back_seconds:
          # Throw away everything before that index
          self.cached_values[field] = cache[keep_index:]
          break

  ############################
  def transform(self, record, timestamp_dict=None):
    """Incorporate any useable fields in this record, and if it gives
    us any new subsampled values, aggregate and return them.
    """
    # Clean out old data
    self._add_record(record)

    # Clean out old data
    self._clean_cache()

    now = time.time()

    result = {}
    for field in self.field_list:
      if not self.cached_values[field]:
        continue

      output_field = self.field_spec[field].get('output', None)
      if not output_field:
        logging.warning('No "output" spec found for field %s', field)
        continue
      algorithm = self.field_spec[field].get('subsample', None)
      if not algorithm:
        logging.warning('No "subsample" spec found for field %s', field)
        continue
      field_result = subsample(algorithm, self.cached_values[field],
                               self.last_timestamp[field], now)
      if field_result:
        result[output_field] = field_result
        self.last_timestamp[field] = field_result[-1][0]

    if result:
      return {'fields': result}
    else:
      return None
