#!/usr/bin/env python3
"""Compute true winds by processing and aggregating vessel
course/speed/heading and relative wind dir/speed records.

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
import time

from pprint import pformat

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord, to_das_record_list  # noqa: E402
from logger.utils.truewinds.truew import truew  # noqa: E402
from logger.transforms.derived_data_transform import DerivedDataTransform  # noqa: E402


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
                 update_on_fields=[],
                 zero_line_reference=0,
                 convert_wind_factor=1,
                 convert_speed_factor=1,
                 metadata_interval=None):
        """
        ```
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

        metadata_interval - how many seconds between when we attach field metadata
                     to a record we send out.
        ```
        """
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

        self.metadata_interval = metadata_interval
        self.last_metadata_send = 0

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
    def _metadata(self):
        """Return a dict of metadata for our derived fields."""

        metadata_fields = {
            self.true_dir_name: {
                'description': 'Derived true wind direction from %s, %s, %s, %s, %s'
                % (self.course_field, self.speed_field, self.heading_field,
                   self.wind_dir_field, self.wind_speed_field),
                'units': 'degrees',
                'device': 'TrueWindTransform',
                'device_type': 'DerivedTrueWindTransform',
                'device_type_field': self.true_dir_name
            },
            self.true_speed_name: {
                'description': 'Derived true wind speed from %s, %s, %s, %s, %s'
                % (self.course_field, self.speed_field, self.heading_field,
                   self.wind_dir_field, self.wind_speed_field),
                'units': 'depends on conversion used for %s (%g) and %s (%g)'
                % (self.speed_field, self.convert_speed_factor,
                   self.wind_speed_field, self.convert_wind_factor),
                'device': 'TrueWindTransform',
                'device_type': 'DerivedTrueWindTransform',
                'device_type_field': self.true_speed_name
            },
            self.apparent_dir_name: {
                'description': 'Derived apparent wind speed from %s, %s, %s, %s, %s'
                % (self.course_field, self.speed_field, self.heading_field,
                   self.wind_dir_field, self.wind_speed_field),
                'units': 'degrees',
                'device': 'TrueWindTransform',
                'device_type': 'DerivedTrueWindTransform',
                'device_type_field': self.apparent_dir_name
            }
        }
        return metadata_fields

    ############################
    def transform(self, record):
        """Incorporate any useable fields in this record, and if it gives
        us a new true wind value, return the results."""

        if record is None:
            return None

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list.
        if type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record))
            return results

        results = []
        for das_record in to_das_record_list(record):
            # If they haven't specified specific fields we should wait for
            # before updates, plan to emit an update after every new record
            # we process. Otherwise, assume we're not going to update unless
            # we see one of the named fields.
            if not self.update_on_fields:
                update = True
            else:
                update = False

            timestamp = das_record.timestamp
            if not timestamp:
                logging.info('DASRecord is missing timestamp - skipping')
                continue

            # Get latest values for any of our fields
            fields = das_record.fields
            if self.course_field in fields:
                if timestamp >= self.course_val_time:
                    self.course_val = fields.get(self.course_field)
                    self.course_val_time = timestamp
                    if self.course_field in self.update_on_fields:
                        update = True

            if self.speed_field in fields:
                if timestamp >= self.speed_val_time:
                    self.speed_val = fields.get(self.speed_field)
                    self.speed_val *= self.convert_speed_factor
                    self.speed_val_time = timestamp
                    if self.speed_field in self.update_on_fields:
                        update = True

            if self.heading_field in fields:
                if timestamp >= self.heading_val_time:
                    self.heading_val = fields.get(self.heading_field)
                    self.heading_val_time = timestamp
                    if self.heading_field in self.update_on_fields:
                        update = True

            if self.wind_dir_field in fields:
                if timestamp >= self.wind_dir_val_time:
                    self.wind_dir_val = fields.get(self.wind_dir_field)
                    self.wind_dir_val_time = timestamp
                    if self.wind_dir_field in self.update_on_fields:
                        update = True

            if self.wind_speed_field in fields:
                if timestamp >= self.wind_speed_val_time:
                    self.wind_speed_val = fields.get(self.wind_speed_field)
                    self.wind_speed_val *= self.convert_wind_factor
                    self.wind_speed_val_time = timestamp
                    if self.wind_speed_field in self.update_on_fields:
                        update = True

            if None in (self.course_val, self.speed_val, self.heading_val,
                        self.wind_dir_val, self.wind_speed_val):
                logging.debug('Not all required values for true winds are present: '
                              'time: %s: %s: %s, %s: %s, %s: %s, %s: %s, %s: %s',
                              timestamp,
                              self.course_field, self.course_val,
                              self.speed_field, self.speed_val,
                              self.heading_field, self.heading_val,
                              self.wind_dir_field, self.wind_dir_val,
                              self.wind_speed_field, self.wind_speed_val)
                continue

            # If we've not seen anything that updates fields that would
            # trigger a new true winds value, skip rest of computation.
            if not update:
                logging.debug('No update needed')
                continue

            logging.debug('Computing new true winds')
            (true_dir, true_speed, apparent_dir) = truew(crse=self.course_val,
                                                         cspd=self.speed_val,
                                                         hd=self.heading_val,
                                                         wdir=self.wind_dir_val,
                                                         zlr=self.zero_line_reference,
                                                         wspd=self.wind_speed_val)

            logging.debug('Got true winds: dir: %s, speed: %s, apparent_dir: %s',
                          true_dir, true_speed, apparent_dir)
            if None in (true_dir, true_speed, apparent_dir):
                logging.info('Got invalid true winds')
                continue

            # If here, we've got a valid new true wind result
            true_wind_fields = {self.true_dir_name: true_dir,
                                self.true_speed_name: true_speed,
                                self.apparent_dir_name: apparent_dir}

            # Add in metadata if so specified and it's been long enough since
            # we last sent it.
            now = time.time()
            if self.metadata_interval and \
               now - self.metadata_interval > self.last_metadata_send:
                metadata = {'fields': self._metadata()}
                self.last_metadata_send = now
                logging.debug('Emitting metadata: %s', pformat(metadata))
            else:
                metadata = None

            results.append(DASRecord(timestamp=timestamp, fields=true_wind_fields,
                                     metadata=metadata))

        return results
