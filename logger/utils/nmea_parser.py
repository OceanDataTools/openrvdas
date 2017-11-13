#!/usr/bin/env python3

"""Tools for parsing.

TODO: should we just 
"""

import glob
import logging
import sys

sys.path.append('.')

from utils import read_json, scanf
from logger.utils.das_record import DASRecord
from logger.utils.timestamp import timestamp

MESSAGE_PATH = 'local/message/*.json'
SENSOR_PATH = 'local/sensor/*.json'
SENSOR_MODEL_PATH = 'local/sensor_model/*.json'

################################################################################
class NMEAParser:
  ############################
  def __init__(self, message_path=MESSAGE_PATH,
               sensor_path=SENSOR_PATH,
               sensor_model_path=SENSOR_MODEL_PATH):
    self.messages = self.read_definitions(message_path)
    self.sensor_models = self.read_definitions(sensor_model_path)
    self.sensors = self.read_definitions(sensor_path)

  ############################
  # Receive an id-prefixed, timestamped NMEA record
  def parse_record(self, nmea_record):
    if not nmea_record:
      return None
    if not type(nmea_record) == type(''):
      logging.error('Record is not NMEA string: "%s"', nmea_record)
      return None
    try:
      (data_id, raw_ts, message) = nmea_record.split(sep=' ', maxsplit=2)
      ts = timestamp(raw_ts)
    except ValueError:
      logging.error('Record not in <data_id> <timestamp> <NMEA> format: "%s"',
                    nmea_record)
      return None
    
    sensor = self.sensors.get(data_id, None)
    if not sensor:
      logging.error('Unrecognized data_id ("%s") in record: %s',
                    data_id, nmea_record)
      return None

    model_name = sensor.get('model', None)
    if not model_name:
      logging.error('No "model" for sensor %s', sensor)
      return None

    # If something goes wrong during parsing, we'll get a ValueError
    try:
      (raw_fields, message_type) = self.parse_nmea(sensor_model_name=model_name,
                                                   message=message)
    except ValueError as e:
      logging.error(str(e))
      return None
    
    # Finally, convert field values to variable names specific to sensor
    sensor_fields = sensor.get('fields', None)
    if not sensor_fields:
      logging.error('No "fields" definition found for sensor %s', data_id)
      return None
    
    fields = {}
    for field_name in raw_fields:
      var_name = sensor_fields.get(field_name, None)
      if var_name:
        fields[var_name] = raw_fields[field_name]

    return DASRecord(data_id=data_id, message_type=message_type,
                     timestamp=ts, fields=fields)

  ############################
  # Parse a raw NMEA message
  def parse_nmea(self, sensor_model_name, message):
    sensor_model = self.sensor_models.get(sensor_model_name, None)
    if not sensor_model:
      logging.error('No sensor_model found matching "%s"' % sensor_model_name)
      return None

    # Get the message type and format. By default (if sensor only
    # emits one type of message), there is no "messages" field, and
    # message type is empty.
    message_type = ''
    sensor_messages = sensor_model.get('messages', None)

    # If our sensor_model doesn't contain a 'messages' field, then the
    # model itself contains the message definition in terms of a
    # 'format' and 'fields' definition.
    if not sensor_messages:
      message_def = sensor_model

    # Otherwise, we need to look up the appropriate message to get
    # format and fields.
    else:
      #  Split off the first element of our message, which
      # should match one of the message types our sensor model knows
      # about.
      (message_type, message) = message.split(sep=',', maxsplit=1)
      if not message_type in sensor_messages:
        raise ValueError('Message type "%s" does not match any message type '
                         'for sensor model %s' % (message_type,
                                                  sensor_model_name))

      message_def = self.messages.get(message_type, None)
      if not message_def:
        raise ValueError('Record message type "%s" does not match any known '
                         'message type: %s' % (message_type, message))

      # If this message_def itself contains a 'message' field, then
      # we've got sub-message types, e.g. $PSXN,23. So iteratively
      # split off the next element, tack it onto the message_type, and
      # figure out which sub-message type we have.
      while message_def.get('messages', None):
        (message_type_element, message) = message.split(sep=',', maxsplit=1)
        message_type += '-' + message_type_element

        message_def = message_def['messages'].get(message_type_element, None)
        if not message_def:
          raise ValueError('Record message type "%s" does not match any known '
                           'message type: %s' % (message_type, message))
          
    # If we've fallen out here, our message_def should no longer
    # have a 'messages' field, but should have 'format' and
    # 'fields', uh, fields defined.
    format = message_def.get('format', None)
    if not format:
      raise ValueError('Model %s has neither "messages" nor "format" defined'
                       % sensor_model_name)        
    fields = message_def.get('fields', None)
    if not fields:
      raise ValueError('Model %s has format but no fields' % sensor_model_name)

    # Here, we should have format and fields both defined - try scanf
    # on our message (or what's left of it after parsing off
    # message_type fields).
    values = scanf.scanf(format, message)
    if not values:
      raise ValueError('%s: %s message format "%s" does not match message: %s'
                       % (sensor_model_name, message_type, format, message))

    # Did we get the right number of values?
    if not len(values) == len(fields):
      raise ValueError('Number of values (%d) does not match number of fields '
                       '(%d): %s != %s' % (len(values), len(fields),
                                           values, fields))
    
    # If still okay, map values to their field names and data types
    field_values = {}
    for i in range(len(values)):
      (name, data_type) = fields[i]
      field_values[name] = self.convert(values[i], data_type)
    return (field_values, message_type)
    
  ############################
  def convert(self, value, data_type):
    if value is '':
      return None
    if not data_type:
      return value
    elif data_type == 'int':
      return int(value)
    elif data_type == 'float':
      return float(value)
    elif data_type == 'str':
      return str(value)
    else:
      raise ValueError('Unknown data type in field definition: "%s"'%data_type)

  ############################
  def read_definitions(self, json_path):
    definitions = {}
    for filename in glob.glob(json_path):
      new_defs = read_json.read_json(filename)
      for key in new_defs:
        if key in definitions:
          logging.warning('Duplicate definition for key "%s" found in %s',
                          key, filename)
        definitions[key] = new_defs[key]
    return definitions
