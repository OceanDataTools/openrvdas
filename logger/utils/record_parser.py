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
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import read_config  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402

# Dict of format types that extend the default formats recognized by the
# parse module.
from logger.utils.record_parser_formats import extra_format_types  # noqa: E402

DEFAULT_DEFINITION_PATH = 'local/devices/*.yaml'
DEFAULT_RECORD_FORMAT = '{data_id:w} {timestamp:ti} {field_string}'


class RecordParser:
    ############################
    def __init__(self, record_format=None,
                 field_patterns=None, metadata=None,
                 definition_path=DEFAULT_DEFINITION_PATH,
                 return_das_record=False, return_json=False,
                 metadata_interval=None, strip_unprintable=False,
                 quiet=False, prepend_data_id=False, delimiter=':'):
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
            of looking for device definitions along the definition path,
            or a dict of message_type:[parse_pattern, parse_pattern].

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

        strip_unprintable
                Strip out and ignore any leading or trailing non-printable binary
                characters in the string to be parsed.

        quiet - if not False, don't complain when unable to parse a record.

        prepend_data_id - If true prepend the instrument data_id to field_names
            in the record.

        delimiter
            The string to insert between data_id and field_name when prepend_data_id is true.
            Defaults to ':'.
            Not used if prepend_data_id is false.
        ```
        """
        self.strip_unprintable = strip_unprintable
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
        self.prepend_data_id = prepend_data_id
        self.delimiter = delimiter

        # If we've been explicitly given the field_patterns we're to use for
        # parsing, compile them now. Patterns may either be a list of strings,
        # a dict of strings or a dict of lists of strings.
        if field_patterns:
            self.compiled_field_patterns = self._compile_formats_from_patterns(field_patterns)
            self.metadata = metadata

        # If we've not been given field_patterns to use for parsing, read in all
        # the devices and device types to compile them.
        else:
            # Fill in the devices and device_types - NOTE: we won't be using
            # these if 'field_patterns' is provided as an argument.
            definitions = self._new_read_definitions(definition_path)
            self.devices = definitions.get('devices', {})
            self.device_types = definitions.get('device_types', {})

            # Some limited error checking: make sure that all devices have a
            # defined device_type.
            for device, device_def in self.devices.items():
                device_type = device_def.get('device_type', None)
                if not device_type:
                    raise ValueError('Device definition for "%s" has no declaration of '
                                     'its device_type.' % device)
                if device_type not in self.device_types:
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
                compiled_format = self._compile_formats_from_patterns(format)
                self.device_types[device_type]['compiled_format'] = compiled_format

            # Metadata: If we haven't been handed a dict of metadata, compile it from
            # the devices we've read.
            #
            # It's a map from variable name to the device and device type it
            # came from, along with device type variable and its units and
            # description, if provided in the device type
            # definition. Compiling this information is kind of excruciating
            # and voluminous.
            if not metadata and metadata_interval is not None:
                for device, device_def in self.devices.items():  # e.g. s330
                    device_type_name = device_def.get('device_type', None)  # Seapath330
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

    ############################
    def parse_record(self, record):
        """Parse an id-prefixed text record into a Python dict of data_id,
        timestamp and fields.
        """
        if not record:
            return None
        if not isinstance(record, str):
            if not self.quiet:
                logging.info('Record is not a string: "%s"', record)
            return None
        try:
            # Break record into (by default) data_id, timestamp and field_string
            parsed_record = self.compiled_record_format.parse(record).named
        except (ValueError, AttributeError):
            if not self.quiet:
                logging.warning('Unable to parse record into "%s"', self.record_format)
                logging.warning('Record: %s', record)
            return None

        # Convert timestamp to numeric, if it's there
        timestamp = parsed_record.get('timestamp', None)
        if timestamp is not None and isinstance(timestamp, datetime.datetime):
            timestamp = timestamp.timestamp()
            parsed_record['timestamp'] = timestamp

        # Extract the field string we're going to parse; remove trailing
        # whitespace.
        field_string = parsed_record.get('field_string', None)

        # If we don't have fields, there's nothing to parse
        if field_string is None:
            if not self.quiet:
                logging.warning('No field_string found in record "%s"', record)
            return None

        if self.strip_unprintable:
            field_string = ''.join([c for c in field_string if c.isprintable()])
        field_string = field_string.strip()
        if not field_string:
            if not self.quiet:
                logging.warning('No field_string found in record "%s"', record)
            return None

        fields = {}

        # If we've been given a set of field_patterns to apply, use the
        # first that matches.
        if self.field_patterns:
            data_id = None
            fields, message_type = self._parse_field_string(field_string,
                                                            self.compiled_field_patterns)
        # If we were given no explicit field_patterns to use, we need to
        # count on the record having a data_id that lets us figure out
        # which device, and therefore which field_patterns to try.
        else:
            data_id = parsed_record.get('data_id', None)
            if data_id is None:
                if not self.quiet:
                    logging.warning('No data id found in record: %s', record)
                return None
            fields, message_type = self.parse_for_data_id(data_id, field_string)

        # We should now have a dictionary of fields. If not, go home
        if fields is None:
            if not self.quiet:
                logging.warning('No formats matched field_string "%s"', field_string)
            return None

        # Some folks want the data_id prepended
        if self.prepend_data_id:
            # This conditional dictates whether fields are stored with just the
            # field_name key, or <data_id><delimiter><field_name>
            # Doing some work directly on the fields dict, so we'll take a copy
            # to loop over.
            fields_copy = fields.copy()
            # Reset the fields dict
            fields = {}
            for field in fields_copy:
                # Determine the new "field_name"
                key = '' + data_id + self.delimiter + field
                # Set the value
                fields[key] = fields_copy[field]

        # Remove raw 'field_string' and add parsed 'fields' to parsed_record
        del parsed_record['field_string']
        parsed_record['fields'] = fields
        if message_type:
            parsed_record['message_type'] = message_type

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
                                 message_type=message_type, fields=fields,
                                 metadata=metadata)
            except KeyError:
                return None

        elif self.return_json:
            return json.dumps(parsed_record)
        else:
            return parsed_record

    ############################
    def _parse_field_string(self, field_string, compiled_field_patterns):
        # Default if we don't match anything
        fields = message_type = None

        # If our pattern(s) are just a single compiled parser, try parsing and
        # return with no message type.
        if isinstance(compiled_field_patterns, parse.Parser):
            result = compiled_field_patterns.parse(field_string)
            if result:
                fields = result.named

        # Else, if it's a list, try it out on all the elements.
        elif isinstance(compiled_field_patterns, list):
            for pattern in compiled_field_patterns:
                fields, message_type = self._parse_field_string(field_string, pattern)
                if fields is not None:
                    break

        # If it's a dict, try out on all values, using the key as message type.
        # It's syntactically possible for the internal set of patterns to have
        # their own message types. Not sure why someone would ever create patterns
        # that did this, but if they do, let that override our base one.
        elif isinstance(compiled_field_patterns, dict):
            for message_type, pattern in compiled_field_patterns.items():
                fields, int_message_type = self._parse_field_string(field_string, pattern)
                message_type = int_message_type or message_type
                if fields is not None:
                    break
        else:
            raise ValueError('Unexpected pattern type in parser: %s'
                             % type(compiled_field_patterns))

        return fields, message_type

    ############################
    def parse_for_data_id(self, data_id, field_string):
        """Look up the device and device type for a data_id. Parse the field_string
        according to those formats. If successful, return a tuple of
        (field_dict, message_type), where field_dict is a dict of
        {field_name: field_value}. Return ({}, None) if unable to match a format pattern.
        """
        failure_values = (None, None)
        if not self.devices:
            logging.warning('RecordParser has no device definitions; unable to parse!')
            return failure_values

        # Get device and device_type definitions for data_id
        device = self.devices.get(data_id, None)
        if not device:
            if not self.quiet:
                logging.warning('Unrecognized data id "%s", field string: %s',
                                data_id, field_string)
                logging.warning('Known data ids are: "%s"',
                                ', '.join(self.devices.keys()))
            return failure_values

        device_type = device.get('device_type', None)
        if not device_type:
            if not self.quiet:
                logging.error('Internal error: No "device_type" for device %s!', device)
            return failure_values

        device_definition = self.device_types.get(device_type, None)
        if not device_definition:
            if not self.quiet:
                logging.error('No definition found for device_type "%s"', device_type)
            return failure_values

        compiled_format_patterns = device_definition.get('compiled_format', None)
        parsed_fields, message_type = \
            self._parse_field_string(field_string, compiled_format_patterns)

        # Did we get anything?
        if parsed_fields is None:
            if not self.quiet:
                logging.warning('No formats matched field_string "%s"', field_string)
            return failure_values

        logging.debug('Got fields: %s', pprint.pformat(parsed_fields))

        # Finally, convert field values to variable names specific to device
        device_fields = device.get('fields', None)
        if not device_fields:
            if not self.quiet:
                logging.error('No "fields" definition found for device %s', data_id)
            return failure_values

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
            if isinstance(value, datetime.datetime):
                value = value.timestamp()
            fields[variable_name] = value

        logging.debug('Got fields: %s', pprint.pformat(fields))
        return fields, message_type

    ############################
    def _compile_formats_from_patterns(self, field_patterns):
        """Return a list/dict of patterns compiled from the
        str/list/dict of passed field_patterns.
        """
        if isinstance(field_patterns, str):
            return [parse.compile(format=field_patterns,
                                  extra_types=extra_format_types)]
        elif isinstance(field_patterns, list):
            return [parse.compile(format=p, extra_types=extra_format_types)
                    for p in field_patterns]
        elif isinstance(field_patterns, dict):
            compiled_field_patterns = {}
            for message_type, message_pattern in field_patterns.items():
                compiled_patterns = self._compile_formats_from_patterns(message_pattern)
                compiled_field_patterns[message_type] = compiled_patterns
            return compiled_field_patterns

        else:
            raise ValueError('Passed field_patterns must be str, list or dict. Found %s: %s'
                             % (type(field_patterns), str(field_patterns)))

    ############################
    def _read_definitions(self, filespec_paths):
        """Read the files on the filespec_paths and return dictionary of
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
        """Read the files on the filespec_paths and return dictionary of
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
                        if not isinstance(val, dict):
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
                        if not isinstance(val, dict):
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

                        if isinstance(val, str):
                            val = [val]
                        for filespec in val:
                            new_defs = self._new_read_definitions(filespec, definitions)
                            definitions['devices'].update(new_defs.get('devices', {}))
                            definitions['device_types'].update(new_defs.get('device_types', {}))

                    # If it's not an includes/devices/device_types def, assume
                    # it's a (deprecated) top-level device or device_type
                    # definition. Try adding it to the right place.
                    else:
                        category = val.get('category', None)
                        if category not in ['device', 'device_type']:
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
