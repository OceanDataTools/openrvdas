#!/usr/bin/env python3
"""Compute true winds by processing and aggregating vessel
course/speed/heading and relative wind dir/speed records.

NOTE that this transform is a DerivedDataTransform, so it takes a
different form of input than a generic Transform. See the definition
of DerivedDataTransform for more information.

There are plenty of challenges with computing a universally-accepted
true wind value. Even with the correct algorithm (not a given), unless
the vessel nav and anemometer values have identical timestamps,
there's the question of how one integrates/interpolates/extrapolates
values with different timestamps.

We allow making the simplifying assumption that, e.g., vessel
course/speed/heading is less variable than wind dir/speed, so we will
only produce updated results when we receive new anemometer records. A
more robust approach would be to wait until we got the next vessel
record and interpolate the course/speed/heading values between the two
vessel records (or, conversely, output when we got a vessel record,
using an interpolation of the preceding and following anemometer
readings?).

"""

import logging
import sys

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.timestamp import time_str
from logger.utils.truewinds.truew import truew
from logger.transforms.derived_data_transform import DerivedDataTransform

################################################################################
class TrueWindsTransform(DerivedDataTransform):
  """Transform that computes true winds from vessel
  course/speed/heading and anemometer relative wind speed/dir.
  """
  def __init__(self,
               course_field, speed_field, heading_field,
               wind_dir_field, wind_speed_field,
               true_dir_name,
               true_speed_name,
               apparent_dir_name,
               update_on_fields=None,
               zero_line_reference=0,
               convert_wind_factor=1,
               convert_speed_factor=1):
    """
    course_field
    speed_field
    heading_field
    wind_dir_field
    wind_speed_field
             Field names from which we should take values for
             course, speed over ground, heading, relative wind speed
             and relative wind direction.

    true_dir_name
    true_speed_name
    apparent_dir_name
             Names that should be given to transform output values.

    update_on_fields
             If non-empty, a list of fields, any of whose arrival should
             trigger an output record. If None, generate output when any
             field is updated.

    zero_line_reference
             Angle between bow and zero line on anemometer, referenced
             to ship.

    convert_wind_factor
    convert_speed_factor
             Wind speed and vessel speed may be in different units; e.g
             wind speed in meters/sec and vessel speed in knots. Multiply
             the respective values we get by the respective factors.
             Typically, only one of these will be not equal to 1; e.g. to
             output true winds as meters/sec, we'll leave convert_wind_factor
             as 1 and specify convert_speed_factor=0.5144
    """
    super().__init__()

    self.course_field = course_field
    self.speed_field = speed_field
    self.heading_field = heading_field
    self.wind_dir_field = wind_dir_field
    self.wind_speed_field = wind_speed_field

    self.true_dir_name = true_dir_name
    self.true_speed_name = true_speed_name
    self.apparent_dir_name = apparent_dir_name

    self.update_on_fields = update_on_fields

    self.zero_line_reference = zero_line_reference

    self.convert_wind_factor = convert_wind_factor
    self.convert_speed_factor = convert_speed_factor

    # TODO: It may make sense for us to cache most recent values so
    # that, for example, we can take single DASRecords in the
    # transform() method and use the most recent values we've seen
    # from previous calls.
    self.course_val = None
    self.speed_val = None
    self.heading_val = None
    self.wind_dir_val = None
    self.wind_speed_val = None

    self.course_val_time = 0
    self.speed_val_time = 0
    self.heading_val_time = 0
    self.wind_dir_val_time = 0
    self.wind_speed_val_time = 0

  ############################
  def fields(self):
    """Which fields are we interested in to produce transformed data?"""
    return [self.course_field, self.speed_field, self.heading_field,
            self.wind_dir_field, self.wind_speed_field]

  ############################
  def transform(self, value_dict, timestamp_dict=None):
    """Incorporate any useable fields in this record, and if it gives
    us a new true wind value, return the results."""

    if not value_dict or type(value_dict) is not dict:
      logging.warning('Improper type for value dict: %s', type(value_dict))
      return None
    if timestamp_dict and type(timestamp_dict) is not dict:
      logging.warning('Improper type for timestamp dict: %s',
                      type(timestamp_dict))
      return None

    update = False

    course_val = value_dict.get(self.course_field,  None)
    speed_val = value_dict.get(self.speed_field, None)
    heading_val = value_dict.get(self.heading_field, None)
    wind_dir_val = value_dict.get(self.wind_dir_field, None)
    wind_speed_val = value_dict.get(self.wind_speed_field, None)

    if None in (course_val, speed_val, heading_val,
                wind_dir_val, wind_speed_val):
      logging.debug('Not all required values for true winds are present')
      return None

    # If we have timestamps, check our most recent timestamps against
    # what's passed in the dictionary.
    if not timestamp_dict:
      update = True
    else:
      new_course_val_time = timestamp_dict.get(self.course_field, 0)
      if new_course_val_time > self.course_val_time:
        self.course_val_time = new_course_val_time
        if not self.update_on_fields or \
           self.course_field in self.update_on_fields:
          update = True

      new_speed_val_time = timestamp_dict.get(self.speed_field, 0)
      if new_speed_val_time > self.speed_val_time:
        self.speed_val_time = new_speed_val_time
        if not self.update_on_fields or \
           self.speed_field in self.update_on_fields:
          update = True

      new_heading_val_time = timestamp_dict.get(self.heading_field, 0)
      if new_heading_val_time > self.heading_val_time:
        self.heading_val_time = new_heading_val_time
        if not self.update_on_fields or \
           self.heading_field in self.update_on_fields:
          update = True

      new_wind_dir_val_time = timestamp_dict.get(self.wind_dir_field, 0)
      if new_wind_dir_val_time > self.wind_dir_val_time:
        self.wind_dir_val_time = new_wind_dir_val_time
        if not self.update_on_fields or \
           self.wind_dir_field in self.update_on_fields:
          update = True

      new_wind_speed_val_time = timestamp_dict.get(self.wind_speed_field, 0)
      if new_wind_speed_val_time > self.wind_speed_val_time:
        self.wind_speed_val_time = new_wind_speed_val_time
        if not self.update_on_fields or \
           self.wind_speed_field in self.update_on_fields:
          update = True

    # If we've not seen anything that updates fields that would
    # trigger a new true winds value, return None.
    if not update:
      return None

    speed_val *= self.convert_speed_factor
    wind_speed_val *= self.convert_wind_factor

    logging.info('Computing new true winds')
    (true_dir, true_speed, apparent_dir) = truew(crse=course_val,
                                                 cspd=speed_val,
                                                 hd=heading_val,
                                                 wdir=wind_dir_val,
                                                 zlr=self.zero_line_reference,
                                                 wspd=wind_speed_val)

    logging.info('Got true winds: dir: %s, speed: %s, apparent_dir: %s',
                 true_dir, true_speed, apparent_dir)
    if None in (true_dir, true_speed, apparent_dir):
      logging.info('Got invalid true winds')
      return None

    # If here, we've got a valid new true wind result
    result = {self.true_dir_name: true_dir,
              self.true_speed_name: true_speed,
              self.apparent_dir_name: apparent_dir}
    return result
