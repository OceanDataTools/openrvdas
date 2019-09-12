#!/usr/bin/env python3
"""Take in true winds and emit a NMEA MWD string, as per format:

MWD - Wind Direction & Speed
$--MWD, x.x,T,x.x,M,x.x,N,x.x,M*hh<CR><LF>

$--: Talker identifier*
MWD: Sentence formatter*
x.x,T: Wind direction, 0° to 359° true*
x.x,M: Wind direction, 0° to 359° magnetic*
x.x,N: Wind speed, knots*
x.x,M: Wind speed, meters/second*
*hh: Checksum*

We get true wind direction ab initio, but if we don't have access to
vessel's magnetic variation, we can't generate the magnetic wind
direction, so omit if not available.

NOTE that this transform is a DerivedDataTransform, so it takes a
different form of input than a generic Transform. See the definition
of DerivedDataTransform for more information.
"""

import logging
import sys

# For efficient checksum code
from functools import reduce
from operator import xor

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.timestamp import time_str
from logger.utils.truewinds.truew import truew
from logger.transforms.derived_data_transform import DerivedDataTransform

################################################################################
class MWDTransform(DerivedDataTransform):
  """Output a NMEA MWD string, given true wind and (when available)
  magnetic variation.
  """
  def __init__(self,
               true_wind_dir_field,
               true_wind_speed_kt_field=None,
               true_wind_speed_ms_field=None,
               magnetic_variation_field=None,
               talker_id='ALMWD'):
    """
    ```
    true_wind_dir_field
             Field name to look for true wind direction
    true_wind_speed_kt_field
             Field name to look for wind speed in knots. Either this
             or true_wind_speed_ms_field must be non-empty.
    true_wind_speed_ms_field
             Field name to look for wind speed in meters per second.
             Either this or true_wind_speed_kt_field must be non-empty.
    magnetic_variation_field
             Vessel magnetic variation. If omitted, only true winds
             will be emitted.
    talker_id
             Should be format '--MWD' to identify the instrument
             that's creating the message.
    ```
    """
    super().__init__()

    if not (true_wind_speed_kt_field or true_wind_speed_ms_field):
      raise ValueError('MWDTransform: must specify either '
                       'true_wind_speed_kt_field or true_wind_speed_ms_field')

    self.true_wind_dir_field = true_wind_dir_field
    self.true_wind_speed_kt_field = true_wind_speed_kt_field
    self.true_wind_speed_ms_field = true_wind_speed_ms_field
    self.magnetic_variation_field = magnetic_variation_field
    self.talker_id = talker_id

    self.true_wind_dir = None
    self.true_wind_speed_kt = None
    self.true_wind_speed_ms = None
    self.magnetic_variation = None

  ############################
  def fields(self):
    """Which fields are we interested in to produce transformed data?"""
    
    all_fields = [self.true_wind_dir_field,
                  self.true_wind_speed_kt_field,
                  self.true_wind_speed_ms_field,
                  self.magnetic_variation_field,
    ]
    # Only ask for non-None fields
    return [f for f in all_fields if f is not None]

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
    fields = value_dict.get('fields', None)
    if not fields:
      logging.debug('MWDTransform got record with no fields: %s', value_dict)
      return None
    
    # Grab any relevant values
    self.true_wind_dir = fields.get(self.true_wind_dir_field,
                                    self.true_wind_dir)
    if self.true_wind_speed_kt_field:
      self.true_wind_speed_kt = fields.get(self.true_wind_speed_kt_field,
                                           self.true_wind_speed_kt)
    if self.true_wind_speed_ms_field:
      self.true_wind_speed_ms = fields.get(self.true_wind_speed_ms_field,
                                           self.true_wind_speed_ms)
    if self.magnetic_variation_field:
      self.magnetic_variation = fields.get(self.magnetic_variation_field,
                                           self.magnetic_variation)

    #logging.debug('Got record: %s\n%s %s %s', fields, self.true_wind_dir,
    #              self.true_wind_speed_kt, self.true_wind_speed_ms)

    # Do we have enough values to emit a record? If not, go home.
    if self.true_wind_dir is None:
      logging.debug('Not all required values present - skipping')
      return None
    if self.true_wind_speed_kt is None and self.true_wind_speed_ms is None:
      logging.debug('Not all required values present - skipping')
      return None

    # Are we filling in meters per second from knots?
    if self.true_wind_speed_ms_field is None and \
       self.true_wind_speed_kt_field and \
       self.true_wind_speed_kt is not None:
      self.true_wind_speed_ms = self.true_wind_speed_kt * 0.514444

    # Are we filling in knots from meters per second from?
    if self.true_wind_speed_kt_field is None and \
       self.true_wind_speed_ms_field and \
       self.true_wind_speed_ms is not None:
      self.true_wind_speed_kt = self.true_wind_speed_kt * 1.94384

    # Do we have a magnetic variation? If so, provide mag winds,
    # otherwise use an empty string.
    if self.magnetic_variation is not None:
      mag_winds = '%3.1f' % (self.true_wind_dir - self.magnetic_variation)
    else:
      mag_winds = ''

    # Assemble string, compute checksum, and return it.
    result_str = '%s,%3.1f,T,%s,M,%3.1f,N,%3.1f,M' % \
                 (self.talker_id, self.true_wind_dir, mag_winds,
                   self.true_wind_speed_kt, self.true_wind_speed_ms)
    checksum = reduce(xor, (ord(c) for c in result_str))
    return '$%s*%02X\r\n' % (result_str, checksum)
