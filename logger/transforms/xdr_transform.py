#!/usr/bin/env python3
"""Take in true winds and emit a NMEA XDR string, as per format:

  $--XDR,a,x.x,a,c--c, ..... *hh<CR><LF> \\
Field Number:
1) Transducer Type
2) Measurement Data
3) Units of measurement
4) Name of transducer
x) More of the same
n) Checksum
Example:
$IIXDR,C,19.52,C,TempAir*19
$IIXDR,P,1.02481,B,Barometer*29
Measured Value | Transducer Type | Measured Data   | Unit of measure | Transducer Name
------------------------------------------------------------------------------------------------------
barometric     | "P" pressure    | 0.8..1.1 or 800..1100           | "B" bar         | "Barometer"
air temperature| "C" temperature |   2 decimals                    | "C" celsius     | "TempAir" or "ENV_OUTAIR_T"
pitch          | "A" angle       |-180..0 nose down 0..180 nose up | "D" degrees     | "PTCH" or "PITCH"
rolling        | "A" angle       |-180..0 L         0..180 R       | "D" degrees     | "ROLL"
water temp     | "C" temperature |   2 decimals                    | "C" celsius     | "ENV_WATER_T"
-----------------------------------------------------------------------------------------------------

We're going to cheat a bit here, as traditionally, a Transform is only
supposed to output zero or one record for every input record it
gets. We're going to emit multiple records as separate lines in a
single record and count on whatever gets them next (UDPWriter or
TextFileWriter, for example) acting appropriately.

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

############################
def checksum(source):
  """Return hex checksum for source string."""
  return '%02X' % reduce(xor, (ord(c) for c in source))

################################################################################
class XDRTransform(DerivedDataTransform):
  """Output a NMEA XDR string, given whatever variables we can find.
  """
  def __init__(self,
               barometer_field=None,
               barometer_output_field=None,
               air_temp_field=None,
               air_temp_output_field=None,
               sea_temp_field=None,
               sea_temp_output_field=None,
               talker_id='ALXDR'):
    """
    ```
    barometer_field
             Name of field that contains barometric pressure.
    barometer_output_field
             Transducer name of that should be output with barometer data.
             Defaults to barometer_field.
    air_temp_field
             Name of field that contains air temperature
    air_temp_output_field
             Transducer name of that should be output with air temp data.
             Defaults to air_temp_field.
    sea_temp_field
             Name of field that contains water temperature
    sea_temp_output_field
             Transducer name of that should be output with sea temp data.
             Defaults to sea_temp_field.
    talker_id
             Should be format '--XDR' to identify the instrument
             that's creating the message.
    ```
    """
    super().__init__()

    self.barometer_field = barometer_field
    self.barometer_output_field = barometer_output_field or barometer_field
    self.air_temp_field = air_temp_field
    self.air_temp_output_field = air_temp_output_field or air_temp_field
    self.sea_temp_field = sea_temp_field
    self.sea_temp_output_field = sea_temp_output_field or air_temp_field
    self.talker_id = talker_id

  ############################
  def fields(self):
    """Which fields are we interested in to produce transformed data?"""
    
    all_fields = [self.barometer_field, self.air_temp_field, self.sea_temp_field]
    # Only ask for non-None fields
    return [f for f in all_fields if f is not None]

  ############################
  def transform(self, value_dict, timestamp_dict=None):
    """Incorporate any useable fields in this record, and if it gives us a
    new true wind value, return the results.
    """
    if not value_dict or type(value_dict) is not dict:
      logging.warning('Improper type for value dict: %s', type(value_dict))
      return None

    fields = value_dict.get('fields', None)
    if not fields:
      logging.debug('XDRTransform got record with no fields: %s', value_dict)
      return None
    
    result_str = ''
    # Grab any relevant values
    if self.barometer_field in fields:
      barometer = fields.get(self.barometer_field)
      barometer_data = '%s,P,%s,B,%s' % (self.talker_id, barometer,
                                         self.barometer_output_field)
      barometer_str = '$%s*%s\r\n' % (barometer_data, checksum(barometer_data))
      result_str += barometer_str

    if self.air_temp_field in fields:
      air_temp = fields.get(self.air_temp_field)
      air_temp_data = '%s,C,%3.2f,C,%s' % (self.talker_id, float(air_temp),
                                           self.air_temp_output_field)
      air_temp_str = '$%s*%s\r\n' % (air_temp_data, checksum(air_temp_data))
      result_str += air_temp_str

    if self.sea_temp_field in fields:
      sea_temp = fields.get(self.sea_temp_field)
      sea_temp_data = '%s,C,%3.2f,C,%s' % (self.talker_id, float(sea_temp),
                                           self.sea_temp_output_field)
      sea_temp_str = '$%s*%s\r\n' % (sea_temp_data, checksum(sea_temp_data))
      result_str += sea_temp_str

    # If any of our values are there, return the result string
    return result_str or None
