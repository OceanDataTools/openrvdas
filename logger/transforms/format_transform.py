#!/usr/bin/env python3
"""
Sample config file for using for FormatTransform. To run, copy the config
below to a file, say 's330_format.yaml', then run

  logger/listener/listen.py --config_file s330_format.yaml

Sample config:

    # Read from stored logfile
    readers:
      class: LogfileReader
      kwargs:
        filebase: test//NBP1406/s330/raw/NBP1406_s330-2014-08-01

    # Logfile reader already has a timestamp, so we don't need to
    # timestamp. Just add the instrument prefix and parse it.
    transforms:
    - class: PrefixTransform
      kwargs:
        prefix: s330
    - class: ParseTransform
      kwargs:
        definition_path: local/usap/nbp/devices/nbp_devices.yaml

    # Output a string showing course and speed. We only provide a default
    # for course, so if course is missing, we will still output a string, but
    # if speed is missing, we will output None instead of a string.
    - class: FormatTransform
      module: logger.transforms.format_transform  # where the definition is
      kwargs:
        format_str: 'Course: {S330CourseTrue}, Speed: {S330SpeedKt}'
        defaults: {'S330CourseTrue': '-'}

    # Output to stdout
    writers:
    - class: TextFileWriter
"""

import sys
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class FormatTransform(Transform):
    def __init__(self, format_str, defaults=None):
        """
        Output a formatted string in which field values from a DASRecord or field
        dict have been substituted. An optional default_dict may be provided to
        indicate what value should be substituted in if the relevant record is
        missing any of the requested values.

        format_str   - A format string, as described
                       https://www.w3schools.com/python/ref_string_format.asp

                       E.g. format_str='Course: {S330CourseTrue}, Speed: {S330SpeedKt}kt',
                       would output 'Course: 227.3, Speed 7.3kt'


        default_dict - If omitted, transform will emit None if any of the fields
                       requested in the format string are missing.

                       If not None, should be a dict of field:value pairs
                       specifying the value that should be substituted in
                       for any missing fields. If a field:value pair is missing
                       from this dict, return None for the relevant record.

                       E.g. default_dict={'S330CourseTrue': '-'} would output
                       'Course: -, Speed 7.3kt' if S330CourseTrue were missing
                       from the input record, but would output None if S330SpeedKt
                       were missing (because no default was provided for
                       S330SpeedKt).
        """

        self.format_str = format_str
        self.defaults = defaults or {}

    def transform(self, record):
        # Make sure record is right format - DASRecord or dict
        if not record:
            return None

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list.
        if type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record))
            return results

        if type(record) is DASRecord:
            record_fields = record.fields
        elif type(record) is dict:
            if 'fields' in record:
                record_fields = record['fields']
            else:
                record_fields = record
        else:
            return ('Record passed to FormatTransform was neither a dict nor a '
                    'DASRecord. Type was %s: %s' % (type(record), str(record)[:80]))

        fields = self.defaults.copy()

        for field, value in record_fields.items():
            fields[field] = value

        # Add the timestamp as a field as well.
        if type(record) is DASRecord:
          fields['timestamp'] = record.timestamp
        else:
          fields['timestamp'] = record.get('timestamp', 0)

        try:
            result = self.format_str.format(**fields)

        except KeyError:
            result = None

        if result:
            return result
        return None
