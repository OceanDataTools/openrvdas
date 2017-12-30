#!/usr/bin/env python3
"""Compute true winds by processing and aggregating vessel
course/speed/heading and relative wind dir/speed records.

There are plenty of challenges with computing a universally-accepted
true wind value. Even with the correct algorithm (not a given), unless
the vessel nav and anemometer values have identical timestamps,
there's the question of how one integrates/interpolates/extrapolates
values with different timestamps.

Below, we make the simplifying assumption that vessel
course/speed/heading is less variable than wind dir/speed, so we cache
the most recent vessel record when we receive it, and only output a
true wind estimate when we receive new anemometer records. A more
robust approach would be to wait until we got the next vessel record
and interpolate the course/speed/heading values between the two vessel
records (or, conversely, output when we got a vessel record, using an
interpolation of the preceding and following anemometer readings?).

TODO: a subclass that expects NMEA input and parses it into DASRecords.
"""

import logging
import sys

sys.path.append('.')

from logger.utils import formats
from logger.utils.das_record import DASRecord
from logger.utils.timestamp import time_str
from logger.utils.truewinds.truew import truew
from logger.transforms.transform import Transform

################################################################################
class TrueWindsTransform(Transform):
  """Transform that computes true winds from vessel
  course/speed/heading and anemometer relative wind speed/dir.
  """
  def __init__(self, data_id, course_fields, speed_fields, heading_fields,
               wind_dir_fields, wind_speed_fields,
               update_on_fields=None,
               zero_line_reference=0,
               convert_wind_factor=1,
               convert_speed_factor=1,
               output_nmea=False):
    """
    data_id
             The data_id that will be attached to the records produced.

    course_fields
    speed_fields
    heading_fields
    wind_dir_fields
    wind_speed_fields
             Comma-separated lists of field names from which we should
             take values for course, speed over ground, heading, relative
             wind speed and relative wind direction.

    update_on_fields
             If non-empty, a comma-separated list of fields, any of whose
             arrival should trigger an output record. By default, equal to
             wind_dir_fields.

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

    output_nmea
             If True, output an NMEA-like string.
    """
    super().__init__(input_format=formats.Python_Record,
                     output_format=formats.Text)
    self.data_id = data_id
    self.course_fields = course_fields.split(',')
    self.speed_fields = speed_fields.split(',')
    self.heading_fields = heading_fields.split(',')
    self.wind_dir_fields = wind_dir_fields.split(',')
    self.wind_speed_fields = wind_speed_fields.split(',')

    if update_on_fields:
      self.update_on_fields = update_on_fields.split(',')
    else:
      self.update_on_fields = self.wind_dir_fields
    self.zero_line_reference = zero_line_reference

    self.convert_wind_factor = convert_wind_factor
    self.convert_speed_factor = convert_speed_factor
    self.output_nmea = output_nmea
    
    self.course_val = None
    self.speed_val = None
    self.heading_val = None
    self.wind_dir_val = None
    self.wind_speed_val = None

    self.last_timestamp = 0
    
  ############################
  def transform(self, record):
    """Incorporate any useable fields in this record, and if it gives 
    us a new true wind value, return it."""
    if not record:
      return None

    if not type(record) is DASRecord:
      logging.warning('Improper format record: %s',record)
      return None

    update = False
    for field_name in record.fields:
      if field_name in self.course_fields:
        self.course_val = record.fields[field_name]
      elif field_name in self.speed_fields:
        self.speed_val = record.fields[field_name] * self.convert_speed_factor
      elif field_name in self.heading_fields:
        self.heading_val = record.fields[field_name]
      elif field_name in self.wind_dir_fields:
        self.wind_dir_val = record.fields[field_name]
      elif field_name in self.wind_speed_fields:
        self.wind_speed_val = record.fields[field_name] * self.convert_wind_factor
      
      if field_name in self.update_on_fields:
        update = True

    # If we've not seen anything that updates fields that would
    # trigger a new true winds value, return None.
    if not update:
      return None

    if self.course_val is None:
      logging.info('Still missing course_val')
      return None
    if self.speed_val is None:
      logging.info('Still missing speed_val')
      return None
    if self.heading_val is None:
      logging.info('Still missing heading_val')
      return None
    if self.wind_dir_val is None:
      logging.info('Still missing wind_dir_val')
      return None
    if self.wind_speed_val is None:
      logging.info('Still missing wind_speed_val')
      return None

    logging.info('Computing new true winds')
    (true_dir, true_speed, app_dir) = truew(crse=self.course_val,
                                            cspd=self.speed_val,
                                            hd=self.heading_val,
                                            wdir=self.wind_dir_val,
                                            zlr=self.zero_line_reference,
                                            wspd=self.wind_speed_val)

    logging.info('Got true winds: dir: %s, speed: %s, app_dir: %s',
                 true_dir, true_speed, app_dir)
    if true_dir is None or true_speed is None or app_dir is None:
      logging.info('Got invalid true winds')
      return None

    # If here, we've got a valid new true wind result
    if self.output_nmea:
      new_record = '%s %s %g,%g,%g' % (self.data_id,
                                       time_str(record.timestamp),
                                       true_dir, true_speed, app_dir)
    else:
      new_record = DASRecord(data_id=self.data_id,
                             timestamp=record.timestamp,
                             fields={'TrueWindDir': true_dir,
                                     'TrueWindSpeed': true_speed,
                                     'ApparentWindDir': app_dir})
    return new_record
