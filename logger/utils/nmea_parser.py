#!/usr/bin/env python3

"""Tools for parsing.
"""

import glob
import logging
import re
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import read_config  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.utils.timestamp import timestamp, TIME_FORMAT  # noqa: E402

DEFAULT_MESSAGE_PATH = 'local/message/*.yaml'
DEFAULT_SENSOR_PATH = 'local/sensor/*.yaml'
DEFAULT_SENSOR_MODEL_PATH = 'local/sensor_model/*.yaml'

RAW_FIELDS_RE = '(?P<raw_fields>[^*]+)'
CHECKSUM_RE = r'(?:\*(?P<checksum>[0-9A-F]{2}))?'
NMEA_RE = re.compile(RAW_FIELDS_RE + CHECKSUM_RE)


class NMEAParser:
    ############################
    def __init__(self, message_path=DEFAULT_MESSAGE_PATH,
                 sensor_path=DEFAULT_SENSOR_PATH,
                 sensor_model_path=DEFAULT_SENSOR_MODEL_PATH,
                 time_format=None):
        self.messages = self._read_definitions(message_path)
        self.sensor_models = self._read_definitions(sensor_model_path)
        self.sensors = self._read_definitions(sensor_path)
        self.time_format = time_format or TIME_FORMAT

    ############################
    def parse_record(self, nmea_record):
        """Receive an id-prefixed, timestamped NMEA record."""
        if not nmea_record:
            return None
        if not isinstance(nmea_record, str):
            logging.info('Record is not NMEA string: "%s"', nmea_record)
            return None
        try:
            (data_id, raw_ts, message) = nmea_record.strip().split(maxsplit=2)
            ts = timestamp(raw_ts, time_format=self.time_format)
        except ValueError:
            logging.info('Record not in <data_id> <timestamp> <NMEA> format: "%s"',
                         nmea_record)
            return None

        # Figure out what kind of message we're expecting, based on data_id
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
            (fields, message_type) = self.parse_nmea(sensor_model_name=model_name,
                                                     message=message)
        except ValueError as e:
            logging.error(str(e))
            return None

        # Finally, convert field values to variable names specific to sensor
        sensor_fields = sensor.get('fields', None)
        if not sensor_fields:
            logging.error('No "fields" definition found for sensor %s', data_id)
            return None

        named_fields = {}
        for field_name in fields:
            var_name = sensor_fields.get(field_name, None)
            if var_name:
                named_fields[var_name] = fields[field_name]

        record = DASRecord(data_id=data_id, message_type=message_type,
                           timestamp=ts, fields=named_fields)
        logging.debug('created DASRecord: %s', str(record))
        return record

    ############################
    def parse_nmea(self, sensor_model_name, message):
        """Parse a raw NMEA message; raise ValueError if there are problems."""
        # Break the message into an optional message_type, the aggregated
        # raw fields and an optional checksum.
        match = NMEA_RE.match(message)
        if not match:
            raise ValueError('Can\'t parse NMEA record: "%s"' % message)

        # Parse out the optional checksum from the raw fields. The first
        # field may be a message type, but we'll deal with that later.
        raw_fields = match.group('raw_fields')
        checksum = match.group('checksum')

        logging.debug('Parsed "%s"', message)
        logging.debug('raw_fields "%s"', raw_fields)
        logging.debug('checksum "%s"', checksum)

        # Proper NMEA uses commas to delimit fields, but some serial
        # instruments use spaces or other characters (Gravimeter, for
        # example, uses both spaces and ':'). Look up sensor model and see
        # if we have a non-default delimiter defined.
        sensor_model = self.sensor_models.get(sensor_model_name, None)
        if not sensor_model:
            raise ValueError('No sensor_model  matching "%s"' % sensor_model_name)

        field_delimiter = sensor_model.get('field_delimiter', ',')
        fields = re.split(field_delimiter, raw_fields)
        logging.debug('fields "%s"', fields)

        # We need to find what fields are defined by this sensor model. If
        # the top-level sensor_model definition has 'fields', then it's
        # easy, and we're done.
        message_type = ''
        definition_base = sensor_model

        # If we don't have 'fields' defined at the top level, it means
        # that this sensor can emit multiple types of messages, which we
        # expect to find under a 'messages' key. We will count on the
        # first element of our field list to tell us which of those
        # messages we've got.
        while 'fields' not in definition_base:
            logging.debug('Iterating with message_type "%s", looking for messages '
                          'in definition_base: %s', message_type, definition_base)

            # If there's no 'fields', there ought to be a 'messages'
            sensor_messages = definition_base.get('messages', None)
            if not sensor_messages:
                raise ValueError('Sensor model %s must have either "fields" or '
                                 '"messages" definition.' % sensor_model_name)

            # We count on the first field in the field list to tell us which
            # message out of our dictionary of messages we actually have.
            element = fields.pop(0)
            message_type = message_type + '-' + element if message_type else element

            definition = sensor_messages.get(element, None)
            if not definition:
                raise ValueError('Message "%s" is not one defined by model %s (%s)'
                                 % (message_type, sensor_model_name, sensor_messages))

            # The value of the 'definition' can be one of two things: 1) a
            # string referring us to a message definition in self.messages,
            # or 2) a dictionary that contains the message definition. Note
            # that the message definition may either directly contain a
            # 'fields' key or may have a 'messages' key defining
            # sub-message_types, requiring us to iterate.

            # If it's a str, it's a reference into the definitions we've
            # previously loaded into self.messages. Look it up, make that
            # our new definition_base and loop.
            if isinstance(definition, str):
                definition_base = self.messages.get(definition, None)
                logging.debug('Definition is reference to message "%s"; loaded: %s',
                              definition, definition_base)
                if not definition_base:
                    raise ValueError('Message definition "%s" (%s) not found for %s'
                                     % (definition, message_type, sensor_model_name))

            # If 'definition' is a dict, make that our new definition_base,
            # tack the element onto our message_type and iterate.
            elif isinstance(definition, dict):
                definition_base = definition

            # If definition is neither dict nor str, something's wrong
            else:
                raise ValueError('Bad definition for %s (%s)'
                                 % (message_type, sensor_model_name))

        # End of while loop. If we're here, we darned well ought to have
        # field_definitions in our definition_base. Get them and make sure
        # they line up with the number of fields we have left.
        field_definitions = definition_base.get('fields')
        if len(fields) != len(field_definitions):
            raise ValueError('Sensor model "%s": %s # of fields (%s) != '
                             '# field definitions (%s): "%s" != "%s"' % (
                                 sensor_model_name, message_type,
                                 len(fields), len(field_definitions),
                                 fields, [f[0] for f in field_definitions]))

        # If still okay, map field values to their definitions
        field_values = {}
        for i in range(len(fields)):
            (name, data_type) = field_definitions[i]
            field_values[name] = self._convert(fields[i], data_type)
        return (field_values, message_type)

    ############################
    def _convert(self, value, data_type):
        if value == '':
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
            raise ValueError('Unknown data type in field definition: "%s"' % data_type)

    ############################
    def _read_definitions(self, filespec_paths):
        definitions = {}
        for filespec in filespec_paths.split(','):
            logging.debug('reading definitions from %s', filespec)
            for filename in glob.glob(filespec):
                new_defs = read_config.read_config(filename)
                for key in new_defs:
                    if key in definitions:
                        logging.warning('Duplicate definition for key "%s" found in %s',
                                        key, filename)
                    definitions[key] = new_defs[key]
        return definitions
