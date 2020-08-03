#!/usr/bin/env python3

"""Tools for parsing NMEA and other text records.

By default, will load device and device_type definitions from files in
local/devices/*.yaml. Please see documentation in
local/devices/README.md for a description of the format these
definitions should take.
"""
import datetime
import glob
import json
import logging
import parse
import pprint
import sys

# Append openrvdas root to syspath prior to importing openrvdas modules
from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils import read_config
from logger.utils.das_record import DASRecord

# Dict of format types that extend the default formats recognized by the
# parse module.
from logger.utils.record_parser_formats import extra_format_types

DEFAULT_DEFINITION_PATH = 'local/devices/*.yaml'
DEFAULT_RECORD_FORMAT = '{data_id:w} {timestamp:ti} {field_string}'

################################################################################
class RecordParser:
  ############################
  def __init__(self, record_format=None,
               field_patterns=None, metadata=None,
               definition_path=DEFAULT_DEFINITION_PATH,
               return_das_record=False, return_json=False,
               metadata_interval=None, quiet=False):
    """Create a parser that will parse field values out of a text record
    and return either a Python dict of data_id, timestamp and fields,
    a JSON encoding of that dict, or a binary DASRecord.
    ```
    record_format - string for parse.parse() to use to break out data_id
        and timestamp from the rest of the message. By default this will
        look for 'data_id timestamp field_string', where 'field_string'
        is a str containing the fields to be parsed.

    field_patterns
        If not None, a list of parse patterns to be tried instead
        of looking for device definitions along the definition path.

    metadata
        If field_patterns is not None, the metadata to send along with
        data records.

    definition_path - a comma-separated set of file globs in which to look
        for device and device_type definitions with which to parse message.

    return_json - return the parsed fields as a JSON encoded dict

    return_das_record - return the parsed fields as a DASRecord object

    metadata_interval - if not None, include the description, units
        and other metadata pertaining to each field in the returned
        record if those data haven't been returned in the last
        metadata_interval seconds.

    quiet - if not False, don't complain when unable to parse a record.
    ```
    """
    self.quiet = quiet
    self.field_patterns = field_patterns
    self.metadata = metadata or {}
    self.record_format = record_format or DEFAULT_RECORD_FORMAT
    self.compiled_record_format = parse.compile(format=self.record_format,
                                                extra_types=extra_format_types)
    self.return_das_record = return_das_record
    self.return_json = return_json
    if return_das_record and return_json:
      raise ValueError('Only one of return_json and return_das_record '
                       'may be true.')

    self.metadata_interval = metadata_interval
    self.metadata_last_sent = {}

    # If we've been explicitly given the field_patterns we're to use for
    # parsing, compile them now.
    if field_patterns:
      self.compiled_field_patterns = [
        parse.compile(format=p, extra_types=extra_format_types)
        for p in field_patterns
      ]

    # If we've not been given field_patterns to use for parsing, read in all
    # the devices and device types to compile them.
    else:
      # Fill in the devices and device_types - NOTE: we won't be using
      # these if 'field_patterns' is provided as an argument.
      definitions = self._new_read_definitions(definition_path)
      self.devices = definitions.get('devices', {})
      self.device_types = definitions.get('device_types', {})

      # If we haven't been handed a dict of metadata, compile it from
      # the devices we've read.
      #
      # It's a map from variable name to the device and device type it
      # came from, along with device type variable and its units and
      # description, if provided in the device type
      # definition. Compiling this information is kind of excruciating
      # and voluminous.
      if not metadata and metadata_interval is not None:
        for device, device_def in self.devices.items(): # e.g. s330
          device_type_name = device_def.get('device_type', None) # Seapath330
          if not device_type_name:
            raise ValueError('Device definition for "%s" has no declaration of '
                             'its device_type.' % device)
          device_type_def = self.device_types.get(device_type_name, None)
          if not device_type_def:
            raise ValueError('Device type "%s" (declared in definition of "%s")'
                             ' is undefined.' % (device_type_name, device))
          device_type_fields = device_type_def.get('fields', None)
          if not device_type_fields:
            raise ValueError('Device type "%s" has no fields?'
                             % device_type_name)

          fields = device_def.get('fields', None)
          if not fields:
            raise ValueError('Device "%s" has no fields?!?' % device)

          # e.g. device_type_field = GPSTime, device_field = S330GPSTime
          for device_type_field, device_field in fields.items():
            # e.g. GPSTime: {'units':..., 'description':...}
            field_desc = device_type_fields.get(device_type_field, None)
            if not field_desc:
              logging.warning('Device type "%s" has no field corresponding to '
                              'device field "%s"' % (device_type_name,
                                                     device_type_field))
              continue
            self.metadata[device_field] = {
              'device': device,
              'device_type': device_type_name,
              'device_type_field': device_type_field,
            }
            self.metadata[device_field].update(field_desc)

      # Some limited error checking: make sure that all devices have a
      # defined device_type.
      for device, device_def in self.devices.items():
        device_type = device_def.get('device_type', None)
        if not device_type:
          raise ValueError('Device definition for "%s" has no declaration of '
                           'its device_type.' % device)
        if not device_type in self.device_types:
          raise ValueError('Device type "%s" (declared in definition of "%s") '
                           'is undefined.' % (device_type, device))

      # Compile format definitions so that we can run them more
      # quickly. If format is a single string, normalize it into a list
      # to simplify later code.
      for device_type, device_type_def in self.device_types.items():
        format = device_type_def.get('format', None)
        if format is None:
          raise ValueError('Device type %s has no format definition'
                           % device_type)
        if type(format) is str:
          try:
            compiled_format = [parse.compile(format=format,
                                             extra_types=extra_format_types)]
          except ValueError as e:
            raise ValueError('Bad parser format: "%s": %s' % (format, e))
        else:
          compiled_format = [parse.compile(format=f,
                                           extra_types=extra_format_types)
                             for f in format]
        self.device_types[device_type]['compiled_format'] = compiled_format

  ############################
  def parse_record(self, record):
    """Parse an id-prefixed text record into a Python dict of data_id,
    timestamp and fields.
    """
    if not record:
      return None
    if not type(record) is str:
      logging.info('Record is not a string: "%s"', record)
      return None
    try:
      parsed_record = self.compiled_record_format.parse(record).named
    except (ValueError, AttributeError):
      if not self.quiet:
        logging.warning('Unable to parse record into "%s"', self.record_format)
        logging.warning('Record: %s', record)
      return None

    # Convert timestamp to numeric, if it's there
    timestamp = parsed_record.get('timestamp', None)
    if timestamp is not None and type(timestamp) is datetime.datetime:
      timestamp = timestamp.timestamp()
      parsed_record['timestamp'] = timestamp

    # Extract the field string we're going to parse; remove trailing
    # whitespace.
    field_string = parsed_record.get('field_string', None).rstrip()
    if field_string is not None:
      del parsed_record['field_string']

    fields = {}
    if field_string:
      # If we've been given a set of field_patterns to apply, use the
      # first that matches.
      if self.field_patterns:
        for trial_pattern in self.compiled_field_patterns:
          parsed_fields = trial_pattern.parse(field_string)
          # Did we find a parse that matched? If so, return its named fields
          if parsed_fields:
            fields = parsed_fields.named
            break

      # If we were given no explicit field_patterns to use, we need to
      # count on the record having a data_id that lets us figure out
      # which device, and therefore which field_patterns to try.
      else:
        data_id = parsed_record.get('data_id', None)
        if data_id is None:
          if not self.quiet:
            logging.warning('No data id found in record: %s', record)
          return None
        fields = self.parse_for_data_id(data_id, field_string)

    if fields:
      parsed_record['fields'] = fields

    # If we have parsed fields, see if we also have metadata. Are we
    # supposed to occasionally send it for our variables? Is it time
    # to send it again?
    metadata_fields = {}
    if self.metadata and self.metadata_interval:
      for field_name in fields:
        last_metadata_sent = self.metadata_last_sent.get(field_name, 0)
        time_since_send = timestamp - last_metadata_sent
        if time_since_send > self.metadata_interval:
          field_metadata = self.metadata.get(field_name, None)
          if field_metadata:
            metadata_fields[field_name] = field_metadata
            self.metadata_last_sent[field_name] = timestamp
    if metadata_fields:
      metadata = {'fields': metadata_fields}
    else:
      metadata = None

    if metadata:
      parsed_record['metadata'] = metadata

    logging.debug('Created parsed record: %s', pprint.pformat(parsed_record))

    # What are we going to do with the result we've created?
    if self.return_das_record:
      try:
        return DASRecord(data_id=data_id, timestamp=timestamp,
                         fields=fields, metadata=metadata)
      except KeyError:
        return None

    elif self.return_json:
      return json.dumps(parsed_record)
    else:
      return parsed_record

  ############################
  def parse_for_data_id(self, data_id, field_string):
    """Look up the device and device type for a data_id. Parse the field_string
    according to those formats, returning a dict of {field_name:
    field_value} or None if unable to match a format pattern.
    """
    if not self.devices:
      logging.warning('RecordParser has no device definitions; unable to parse!')
      return None

    # Get device and device_type definitions for data_id    
    device = self.devices.get(data_id, None)
    if not device:
      if not self.quiet:
        logging.warning('Unrecognized data id "%s", field string: %s',
                        data_id, field_string)
        logging.warning('Known data ids are: "%s"',
                        ', '.join(self.devices.keys()))
      return None

    device_type = device.get('device_type', None)
    if not device_type:
      if not self.quiet:
        logging.error('Internal error: No "device_type" for device %s!', device)
      return None

    # Now parse the field_string, based on device type. If something goes
    # wrong during parsing, expect a ValueError.
    try:
      parsed_fields = self.parse(device_type=device_type, field_string=field_string)
      logging.debug('Got fields: %s', pprint.pformat(parsed_fields))
    except ValueError as e:
      logging.error(str(e))
      return None

    # Finally, convert field values to variable names specific to device
    device_fields = device.get('fields', None)
    if not device_fields:
      if not self.quiet:
        logging.error('No "fields" definition found for device %s', data_id)
      return None

    # Assign field values to the appropriate named variable.
    fields = {}
    for field_name, value in parsed_fields.items():
      variable_name = device_fields.get(field_name, None)
      # None means we're not supposed to report it.
      if variable_name is None:
        continue
      # None means we didn't have a value for this field; omit it.
      if value is None:
        continue
      # If it's a datetime, convert to numeric timestamp
      if type(value) is datetime.datetime:
        value = value.timestamp()
      fields[variable_name] = value

    logging.debug('Got fields: %s', pprint.pformat(fields))
    return fields

  ############################
  def parse(self, device_type, field_string):
    """Parse a text field_string for the given device_type into a flat Python
    dict; raise ValueError if there are problems, return empty dict if
    there is no match to the provided formats.

    """
    device_definition = self.device_types.get(device_type, None)
    if not device_definition:
      raise ValueError('No definition found for device_type "%s"', device_type)

    compiled_format = device_definition.get('compiled_format', None)
    for trial_format in compiled_format:
      fields = trial_format.parse(field_string)
      if fields:
        return fields.named

    # Nothing matched, go home empty-handed
    if not self.quiet:
      logging.warning('No formats for %s matched field_string "%s"',
                      device_type, field_string)
    return {}

  ############################
  def _read_definitions(self, filespec_paths):
    """Read the files on the filespec_paths and return dictinary of
    accumulated definitions.
    """
    definitions = {}
    for filespec in filespec_paths.split(','):
      filenames = glob.glob(filespec)
      if not filenames:
        logging.warning('No files match definition file spec "%s"', filespec)

      for filename in filenames:
        file_definitions = read_config.read_config(filename)

        for new_def_name, new_def in file_definitions.items():
          if new_def_name in definitions:
            logging.warning('Duplicate definition for "%s" found in %s',
                            new_def_name, filename)
          definitions[new_def_name] = new_def
    return definitions

  ############################
  def _new_read_definitions(self, filespec_paths, definitions=None):
    """Read the files on the filespec_paths and return dictinary of
    accumulated definitions.

    filespec_paths - a list of possibly-globbed filespecs to be read

    definitions - optional dict of pre-existing definitions that will
                  be added to. Typically this will be omitted on a base call,
                  but may be added to when recursing. Passing it in allows
                  flagging when items are defined more than once.
    """
    # If nothing was passed in, start with base case.
    definitions = definitions or {'devices': {}, 'device_types': {}}

    for filespec in filespec_paths.split(','):
      filenames = glob.glob(filespec)
      if not filenames:
        logging.warning('No files match definition file spec "%s"', filespec)

      for filename in filenames:
        file_definitions = read_config.read_config(filename)

        for key, val in file_definitions.items():
          # If we have a dict of device definitions, copy them into the
          # 'devices' key of our definitions.
          if key == 'devices':
            if not type(val) is dict:
              logging.error('"devices" values in file %s must be dict. '
                            'Found type "%s"', filename, type(val))
              return None

            for device_name, device_def in val.items():
              if device_name in definitions['devices']:
                logging.warning('Duplicate definition for "%s" found in %s',
                                device_name, filename)
              definitions['devices'][device_name] = device_def

          # If we have a dict of device_type definitions, copy them into the
          # 'device_types' key of our definitions.
          elif key == 'device_types':
            if not type(val) is dict:
              logging.error('"device_typess" values in file %s must be dict. '
                            'Found type "%s"', filename, type(val))
              return None

            for device_type_name, device_type_def in val.items():
              if device_type_name in definitions['device_types']:
                logging.warning('Duplicate definition for "%s" found in %s',
                                device_type_name, filename)
              definitions['device_types'][device_type_name] = device_type_def

          # If we're including other files, recurse inelegantly
          elif key == 'includes':
            if not type(val) in [str, list]:
              logging.error('"includes" values in file %s must be either '
                            'a list or a simple string. Found type "%s"',
                            filename, type(val))
              return None

            if type(val) is str: val = [val]
            for filespec in val:
              new_defs = self._new_read_definitions(filespec, definitions)
              definitions['devices'].update(new_defs.get('devices', {}))
              definitions['device_types'].update(new_defs.get('device_types', {}))

          # If it's not an includes/devices/device_types def, assume
          # it's a (deprecated) top-level device or device_type
          # definition. Try adding it to the right place.
          else:
            category = val.get('category', None)
            if not category in ['device', 'device_type']:
              logging.warning('Top-level definition "%s" in file %s is not '
                              'category "device" or "device_type". '
                              'Category is "%s" - ignoring', category)
              continue
            if category == 'device':
              if key in definitions['devices']:
                logging.warning('Duplicate definition for "%s" found in %s',
                                key, filename)
              definitions['devices'][key] = val
            else:
              if key in definitions['device_types']:
                logging.warning('Duplicate definition for "%s" found in %s',
                                key, filename)
              definitions['device_types'][key] = val

    # Finally, return the accumulated definitions
    return definitions
