#!/usr/bin/env python3
"""Compute specific gravity of seawater from temperature, salinity and
pressure. If pressure is not provided, compute for surface.
"""

import logging
import sys
import time

from pprint import pformat

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord, to_das_record_list
from logger.utils.timestamp import time_str
from logger.utils.truewinds.truew import truew
from logger.transforms.derived_data_transform import DerivedDataTransform

################################################################################
def specific_gravity(temp, salinity, pressure):
  """Compute seawater specific gravity.

  sg = C(p) + β(p)S − α(T, p)T − γ(T, p)(35 − S)T
  units: p in “km”, S in psu, T in ◦C
  C = 999.83 + 5.053p − .048p^2

  β = .808 − .0085p
  α = .0708(1 + .351p + .068(1 − .0683p)T)
  γ = .003(1 − .059p − .012(1 − .064p)T)
  For 30 ≤ S ≤ 40, −2 ≤ T ≤ 30, p ≤ 6 km:
    good to .16 kg/m3
  For 0 ≤ S ≤ 40, good to .3 kg/m3
  """
  C = 999.83 + 5.053 * pressure - 0.048 * pressure * pressure
  beta =  0.808 - 0.0085 * pressure
  alpha = 0.0708 * (1.0 + 0.351*pressure + 0.068 * (1 - 0.0683*pressure) * temp)
  gamma = 0.003 * (1.0 - 0.059*pressure - 0.012 * (1.0 - 0.064*pressure) * temp)

  sg = C + beta * salinity - alpha * temp - gamma * (35 - salinity) * temp
  return sg

################################################################################
class SeawaterSpecificGravityTransform(DerivedDataTransform):
  """Transform that computes true winds from vessel
  course/speed/heading and anemometer relative wind speed/dir.
  """
  def __init__(self,
               temp_field, salinity_field,
               pressure_field=None,
               specific_gravity_name=None, # name of our output field
               update_on_fields = [],
               metadata_interval=None):
    """
    ```
    temp_field
    salinity_field
    pressure_field
             Field names from which we should take values for temperature,
             salinity and pressure. If pressure is omitted, assume surface
             pressure

    specific_gravity_name
             Name to assign to output value

    update_on_fields
             If non-empty, a list of fields, any of whose arrival should
             trigger an output record. If None, generate output when any
             field is updated.

    metadata_interval - how many seconds between when we attach field metadata
                 to a record we send out.
    ```
    """
    self.temp_field = temp_field
    self.salinity_field = salinity_field
    self.pressure_field = pressure_field
    self.specific_gravity_name = specific_gravity_name

    self.update_on_fields = update_on_fields
    self.metadata_interval = metadata_interval
    self.last_metadata_send = 0

    # If we don't have a pressure_field, set pressure_val = 1 for surface.
    self.temp_val = None
    self.salinity_val = None
    self.pressure_val = None if self.pressure_field else 1.0

    self.temp_val_time = 0
    self.salinity_val_time = 0
    self.pressure_val_time = 0

  ############################
  def _metadata(self):
    """Return a dict of metadata for our derived fields."""

    metadata_fields = {
      self.specific_gravity_name:{
        'description': 'Derived specific gravity from temp=%s, '
        'salinity=%s, pressure=%s' % (self.temp_field, self.salinity_field,
                                      self.pressure_field),
        'units': 'kg/m^3',
        'device': 'SeawaterSpecificGravityTransform',
        'device_type': 'SeawaterSpecificGravityTransform',
        'device_type_field': self.specific_gravity_name
      },
    }
    return metadata_fields

  ############################
  def transform(self, record):
    """Incorporate any useable fields in this record, and if it gives
    us a new true wind value, return the results."""

    if record is None: return None

    # If we've got a list, hope it's a list of records. Recurse,
    # calling transform() on each of the list elements in order and
    # return the resulting list.
    if type(record) is list:
      results = []
      for single_record in record:
       results.append(self.transform(single_record))
      return results

    results = []
    for das_record in to_das_record_list(record):
      # If they haven't specified specific fields we should wait for
      # before updates, plan to emit an update after every new record
      # we process. Otherwise, assume we're not going to update unless
      # we see one of the named fields.
      if not self.update_on_fields:
        update = True
      else:
        update = False

      timestamp = das_record.timestamp
      if not timestamp:
        logging.info('DASRecord is missing timestamp - skipping')
        continue

      # Get latest values for any of our fields
      fields = das_record.fields
      if self.temp_field in fields:
        if timestamp >= self.temp_val_time:
          self.temp_val = fields.get(self.temp_field)
          self.temp_val_time = timestamp
          if self.temp_field in self.update_on_fields:
            update = True

      if self.salinity_field in fields:
        if timestamp >= self.salinity_val_time:
          self.salinity_val = fields.get(self.salinity_field)
          self.salinity_val_time = timestamp
          if self.salinity_field in self.update_on_fields:
            update = True

      if self.pressure_field and self.pressure_field in fields:
        if timestamp >= self.pressure_val_time:
          self.pressure_val = fields.get(self.pressure_field)
          self.pressure_val_time = timestamp
          if self.pressure_field in self.update_on_fields:
            update = True

      if None in (self.temp_val, self.salinity_val, self.pressure_val):
        logging.warning('Not all required values for seawater specific gravity '
                      'are present: '
                      'time: %s: %s: %s, %s: %s, %s: %s',
                      timestamp,
                      self.temp_field, self.temp_val,
                      self.salinity_field, self.salinity_val,
                      self.pressure_field, self.pressure_val)
        continue

      # If we've not seen anything that updates fields that would
      # trigger a computation, skip rest of computation.
      if not update:
        logging.debug('No update needed')
        continue

      logging.debug('Computing specific gravity')
      specific_gravity_val = specific_gravity(temp=self.temp_val,
                                              salinity=self.salinity_val,
                                              pressure=self.pressure_val)

      logging.debug('Got seawater specific gravity: %s', specific_gravity_val)

      # If here, we've got a valid specific gravity result
      result_fields = {self.specific_gravity_name: specific_gravity_val}

      # Add in metadata if so specified and it's been long enough since
      # we last sent it.
      now = time.time()
      if self.metadata_interval and \
         now - self.metadata_interval > self.last_metadata_send:
        metadata = {'fields': self._metadata()}
        self.last_metadata_send = now
        logging.debug('Emitting metadata: %s', pformat(metadata))
      else:
        metadata = None

      results.append(DASRecord(timestamp=timestamp, fields=result_fields,
                               metadata=metadata))

    # If we've only got a single result, return it as a singleton
    # rather than as a list.
    if results and len(results) == 1:
      return results[0]
    return results
