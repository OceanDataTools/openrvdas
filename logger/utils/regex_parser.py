#!/usr/bin/env python3

"""Tools for parsing NMEA and other text records using regex.
"""
import datetime
import logging
import re
import pprint
import sys
import time

from os.path import dirname, realpath


# Append openrvdas root to syspath prior to importing openrvdas modules
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord  # noqa: E402

# Note: this is a "permissive" regex. It looks for data_id and timestamp prior to field_string,
# But still parses field_string if they are absent
# Works for both "data_id timestamp fields" but also parses "fields" if
# data_id or timestamp are missing

DEFAULT_RECORD_FORMAT = r"^(?:(?P<data_id>\w+)\s+(?P<timestamp>[0-9TZ:\-\.]*)\s+)?(?P<field_string>(.|\r|\n)*)"  # noqa: E501


################################################################################
class RegexParser:
    ############################
    def __init__(self,
                 record_format=None,
                 field_patterns=None,
                 data_id=None,
                 quiet=False):
        r"""Create a parser that will parse field values out of a text record
        and return a DASRecord object.
        ```
        record_format - string for re.match() to use to break out data_id
            and timestamp from the rest of the message. By default this will
            look for 'data_id timestamp field_string', where 'field_string'
            is a str containing the fields to be parsed.

        field_patterns
            If not None, either
            - a list of regex patterns to be tried
            - a dict of message_type:regex patterns to be tried. When one
              matches, the record's message_type is set accordingly.

        data_id
            If specified, this string is used as the data_id for all records,
            overriding any data_id extracted from the source record.

        quiet - if not False, don't complain when unable to parse a record.
        ```
        """
        self.quiet = quiet
        self.field_patterns = field_patterns
        self.record_format = record_format or DEFAULT_RECORD_FORMAT
        self.compiled_record_format = re.compile(self.record_format)
        self.data_id = data_id  # Store the data_id override

        # If we've been explicitly given the field_patterns we're to use for
        # parsing, compile them now.
        if field_patterns:
            if isinstance(field_patterns, list):
                self.compiled_field_patterns = [
                    re.compile(pattern)
                    for pattern in field_patterns
                ]
            elif isinstance(field_patterns, dict):
                self.compiled_field_patterns = {
                    message_type: re.compile(pattern)
                    for (message_type, pattern) in field_patterns.items()
                }
            else:
                raise ValueError('field_patterns must either be a list of patterns or '
                                 'dict of message_type:pattern pairs. Found type '
                                 f'{type(field_patterns)}')

    ############################
    def parse_record(self, record):
        """Parse an id-prefixed text record into a DASRecord.
        """
        if not record:
            return None
        if not isinstance(record, str):
            logging.info('Record is not a string: "%s"', record)
            return None
        try:
            parsed_record = self.compiled_record_format.match(record).groupdict()
        except (ValueError, AttributeError):
            if not self.quiet:
                logging.warning('Unable to parse record into "%s"', self.record_format)
                logging.warning('Record: %s', record)
            return None

        if parsed_record is None:
            return None

        # Logic to determine data_id:
        # 1. If self.data_id is set (in __init__), use it (Override).
        # 2. Else, look for 'data_id' extracted from the record via regex.
        # 3. If that fails, default to 'unknown'.
        if self.data_id:
            data_id = self.data_id
        else:
            data_id = parsed_record.get('data_id', None)
            if not data_id:
                if not self.quiet:
                    logging.warning('No data_id found in record and none specified. '
                                    'Defaulting to "unknown".')
                data_id = 'unknown'

        # Convert timestamp to numeric, if it's there.
        # Initialize to None first to avoid UnboundLocalError if 'timestamp'
        # is not in the regex groups.
        timestamp = None
        timestamp_text = parsed_record.get('timestamp', None)

        if timestamp_text is not None:
            timestamp = self.convert_timestamp(timestamp_text)

        # If no timestamp found, DASRecord will default to time.time()
        # if passed None.
        if timestamp is None:
            timestamp = time.time()

        # Extract the field string we're going to parse;
        # remove trailing whitespace.
        field_string = parsed_record.get('field_string', None)
        if field_string is not None:
            field_string = field_string.rstrip()

        message_type = None
        fields = {}
        if field_string:
            # If we've been given a set of field_patterns to apply,
            # use the first that matches.
            # Shortcut that lets us iterate through a list or a dict with the same
            # invocation. With a list, it returns (None, value); with a dict it
            # returns (key, value).
            def iterate_patterns(obj):
                return (obj.items() if isinstance(obj, dict) else ((None, v) for v in obj))

            if self.field_patterns:
                for message_type, pattern in iterate_patterns(self.compiled_field_patterns):
                    try:
                        try_parse = pattern.match(field_string)
                        # Did we find a parse that matched?
                        # If so, return its fields
                        if try_parse:
                            fields = try_parse.groupdict()
                            break
                    except Exception as e:
                        logging.error(e)

        logging.debug('Created parsed fields: %s', pprint.pformat(fields))

        try:
            return DASRecord(data_id=data_id, timestamp=timestamp,
                             message_type=message_type,
                             fields=fields)
        except KeyError:
            return None

    ############################
    def convert_timestamp(self, datetime_text):
        """Validates a datetime string and converts to numeric.
        """

        DEFAULT_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'

        try:
            datetime_ti = datetime.datetime.strptime(
                datetime_text, DEFAULT_FORMAT)
        except ValueError:
            logging.debug("Incorrect datetime format.")
            return None

        if datetime_ti:
            # Explicitly set UTC timezone because the format expects 'Z'
            # .replace(tzinfo=...) ensures .timestamp() treats it as UTC
            # regardless of the local system clock.
            timestamp = datetime_ti.replace(tzinfo=datetime.timezone.utc).timestamp()
            return timestamp
