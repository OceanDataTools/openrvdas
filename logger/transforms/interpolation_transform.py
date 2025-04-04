#!/usr/bin/env python3
"""Compute subsamples of input data.
"""

import logging
import sys
import time

from math import degrees, radians, sin, cos, atan2
from statistics import mean
from typing import Union

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.derived_data_transform import DerivedDataTransform  # noqa: E402


################################################################################
class InterpolationTransform(DerivedDataTransform):
    """Transform that computes interpolations of the specified variables.
    """

    def __init__(self, field_spec, interval, window, data_id=None, metadata_interval=None):
        """
        ```
        field_spec - a dict of interpolated variables that are to be created,
                where the key is the new variable's name, and the value is a dict
                specifying the source field name and the algorithm that is to be
                used to do the interpolation. E.g.:

               {
                 'AvgCNAVCourseTrue': {
                   'source': 'CNAVCourseTrue',
                   'algorithm': {
                     'type': 'boxcar_average',
                     'window': 30
                   },
                 },
                 'AvgCNAVGPSDay': {
                   'source': 'CNAVGPSDay',
                   'algorithm': { 'type': 'nearest' },
                 },
                 ...
               }

               To simplify templating, can also accept a spec of the form
               of a list:

               [
                 { sources: [MwxAirTemp, RTMPTemp, ...],
                   algorithm: boxcar_average,
                   window: 10,
                   result_prefix: Avg
                 },
                 { sources: [PortTrueWindDir, StbdTrueWindDir],
                   algorithm: polar_average,
                   window: 10,
                   result_prefix: Avg
                 }
               ]

        interval - At what intervals (in seconds) should the subsampling
               be computed?

        window - Time window (in seconds) of data we should maintain
               around the computation we're going to make.

        data_id - What data id to assign to the output

        metadata_interval - how many seconds between when we attach field metadata
               to a record we send out.
        ```

        """
        self.field_spec = {}
        self.source_fields = set()
        if isinstance(field_spec, dict):
            for result_field, entry in field_spec.items():
                if 'source' in entry and 'algorithm' in entry:
                    self.field_spec[result_field] = entry
                    self.source_fields.add(entry.get('source'))
                else:
                    logging.warning('InterpolationTransform field definition for %s '
                                    'must specify both "source" and "algorithm": %s',
                                    result_field, entry)

        # Alternate way of setting up a field spec that makes it easier to templatize.
        # We'll expand the list of specs into a traditional field_spec
        elif isinstance(field_spec, list):
            for spec_instance in field_spec:
                # Each spec_instance should be a dict of fields:, algorithm:,
                # output_field_prefix: and window:
                if not isinstance(spec_instance, dict):
                    raise ValueError('InterpolationTransform: if field_spec is list, must be '
                                     f'a list of dicts; found list of {type(spec_instance)}')
                sources = spec_instance.get('sources')

                if not isinstance(sources, list):
                    raise ValueError('InterpolationTransform: sources for field spec must be '
                                     f'a list ; found {type(spec_instance)}')

                # Expand source list into a traditional field_spec
                algorithm = spec_instance.get('algorithm')
                window = spec_instance.get('window')
                result_prefix = spec_instance.get('result_prefix')
                for source in sources:
                    entry = {'source': source, 'algorithm': {'type': algorithm, 'window': window}}
                    result_field = result_prefix + source
                    self.field_spec[result_field] = entry

                # Finally, stash sources so we know what to look for
                self.source_fields.update(sources)

        else:
            raise ValueError('InterpolationTransform: field_spec must be either list '
                             f'or dict. Found {type(field_spec)}')

        self.interval = interval
        self.window = window
        self.data_id = data_id
        self.metadata_interval = metadata_interval

        # A dict of the cached values we're hanging onto
        self.cached_values = {f: [] for f in self.source_fields}

        # The next timestamp we'd like to emit. Is set the first time we
        # call transform().
        self.next_timestamp = 0
        self.latest_timestamp = 0
        self.last_metadata_send = 0  # last time we've sent metadata

    ############################
    def fields(self):
        """Which fields are we interested in to produce transformed data?"""
        return list(self.result_fields)

    ############################
    def _metadata(self):
        """Return a dict of metadata for our derived fields."""
        metadata_fields = {
            'field': {
                'description':
                'Subsampled values of %s via %s' %
                (entry['source'], entry['algorithm']),
                'device': 'InterpolationTransform',
                'device_type': 'DerivedDataTransform',
                'device_type_field': result_field
            }
            for result_field, entry in self.field_spec.items()
        }
        return metadata_fields

    ############################
    def _add_record(self, record):
        """Cached the values contained in a new record."""
        if type(record) not in [DASRecord, dict]:
            logging.error('SubsampleTransform records must be dict or '
                          'DASRecord. Received type %s: %s', type(record), record)
            return

        if type(record) is DASRecord:
            timestamp = record.timestamp
            fields = record.fields
        else:
            timestamp = record.get('timestamp', 0)
            fields = record.get('fields')

        if not fields:
            logging.info('InterpolationTransform: record has no fields: %s', record)
            return timestamp

        # First, copy the new data into our cache.  NOTE: It's a judgment
        # call whether it's more efficient to iterate over the fields
        # we're looking for or the fields in the record.
        for field, new_value in fields.items():
            if field not in self.source_fields:
                continue

            # Examine the value we've gotten. If list, we assume it's [(ts,
            # value), (ts, value),...]
            if type(new_value) is list:
                for ts, val in new_value.items():
                    self.cached_values[field].append((ts, val))
                    logging.debug(f'adding {ts}: {field} - {val}')

            # If not list, assume DASRecord or simple field dict; add tuple
            elif timestamp:
                self.cached_values[field].append((timestamp, new_value))
                logging.debug(f'adding {timestamp}: {field} - {new_value}')
            else:
                logging.warning('SubsampleTransform found no timestamp in '
                              'record: %s', record)

        # Return the timestamp of the record
        return timestamp

    ############################
    def _clean_cache(self):
        """Which fields are we interested in to produce transformed data?"""
        for field in self.source_fields:
            # Iterate forward through field cache until we find a timestamp
            # that is recent enough to keep
            cache = self.cached_values[field]
            lower_limit = self.next_timestamp - self.window/2
            keep_index = 0
            while keep_index < len(cache) and cache[keep_index][0] < lower_limit:
                keep_index += 1

            # Throw away everything before that index
            self.cached_values[field] = cache[keep_index:]

    ############################
    def transform(self, record: Union[DASRecord, dict]):
        """Incorporate any useable fields in this record, and if it gives
        us any new interpolated values, aggregate and return them as a list of
        dicts of the form:

        [
          {'timestamp': timestamp,
           'fields': {
             fieldname: value,
             fieldname: value,
             ...
            }
          },
          {'timestamp': timestamp,
           'fields': ...
          }
        ]

        If there are insufficient data in the window to compute any
        interpolation, return an empty list.
        """
        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from Transform()
            return self.digest_record(record)  # inherited from Transform()

        # Add the record and remember its timestamp.
        record_timestamp = self._add_record(record)

        # First time through, our 'next_timestamp' will be zero. Set it to
        # a good starting place.
        if not self.next_timestamp:
            self.next_timestamp = record_timestamp

        self.latest_timestamp = max(self.latest_timestamp, record_timestamp)

        # What fields do we have data for in our cache?
        non_empty = {}
        for dest, spec in self.field_spec.items():
            source = spec.get('source')
            if source:
                values = self.cached_values.get(source, [])
                if len(values):
                    non_empty[dest] = [source, len(values)]

        # Iterate through all timestamps up to the edge of what we can fit
        # in our window without running into the edge of our latest timestamp.
        results = []
        logging.debug(f'latest timestamp: {self.latest_timestamp}, next: {self.next_timestamp}')
        while self.next_timestamp < self.latest_timestamp - self.window/2:
            # Clean out old data
            self._clean_cache()

            result = {}
            for result_field, entry in self.field_spec.items():
                source = entry.get('source')
                source_values = self.cached_values.get(source)
                algorithm = entry.get('algorithm')
                # logging.warning('%s->%s: %d values',
                #                source, result_field, len(source_values))
                value = interpolate(algorithm, source_values,
                                    self.next_timestamp,
                                    self.latest_timestamp)
                if value is not None:
                    result[result_field] = value
            if result:
                result_record = {'timestamp': self.next_timestamp, 'fields': result}
                if self.data_id:
                    result_record['data_id'] = self.data_id
                results.append(result_record)
            self.next_timestamp += self.interval

        return results


############################
def interpolate(algorithm, values, timestamp, now):
    """An omnibus routine for taking a list of timestamped values, a
    specification of an averaging algorithm, and returning a value
    computed at the specified timestamp. Returns None if there aren't
    enough data to compute a value.

    algorithm    The name of the algorithm to be used

    values       A list of [(timestamp, value),...] pairs

    timestamp    The timestamp for which interpolation should be computed

    now          Timestamp now. This should be used to determine whether
                 we're far enough beyond our timestamp to compute a value.
    """
    if not type(algorithm) is dict:
        logging.warning('Function interpolate() handed non-dict algorithm '
                        'specification: %s', algorithm)
        return None
    if not values:
        logging.debug('Function interpolate() handed empty values list')
        return None

    ##################
    # Select algorithm
    alg_type = algorithm.get('type')

    # boxcar_average: all values within symmetric interval window get
    # same weight.
    if alg_type == 'boxcar_average':
        window = algorithm.get('window', 10)  # How far back/forward to average
        lower_limit = timestamp - window/2
        upper_limit = timestamp + window/2
        vals_to_average = [val for ts, val in values
                           if ts >= lower_limit and ts <= upper_limit]
        if not vals_to_average:
            return None

        try:
            return mean(vals_to_average)
        except TypeError:
            logging.error('Non-numeric value in interpolation list: %s', vals_to_average)
            return None

    # nearest: return value of nearest timestamp. Note that we assume
    # timestamps are in order, so once distance starts going up, we're
    # done.
    if alg_type == 'nearest':
        best_distance = float('inf')
        value = None
        for i in range(len(values)):
            ts, ts_value = values[i]
            distance = abs(ts - timestamp)
            if distance <= best_distance:
                best_distance = distance
                value = ts_value
            else:
                break
        return value

    # polar_average: interpret as an angle in degrees. Convert to points
    # on a unit circle and return the angle of their centroid from the origin.
    if alg_type == 'polar_average':
        window = algorithm.get('window', 10)  # How far back/forward to average
        lower_limit = timestamp - window/2
        upper_limit = timestamp + window/2
        vals_to_average = [val for ts, val in values
                           if ts >= lower_limit and ts <= upper_limit]
        if not vals_to_average:
            return None

        try:
            val_radians = [radians(val) for val in vals_to_average]
            x_mean = mean([sin(val) for val in val_radians])
            y_mean = mean([cos(val) for val in val_radians])
            angle = degrees(atan2(x_mean, y_mean))
            if angle < 0:
                angle += 360
            return angle
        except TypeError:
            logging.error('Non-numeric value in interpolation list: %s', vals_to_average)
            return None

    # Not an algorithm we recognize
    else:
        logging.warning('Function interpolate() received unrecognized algorithm '
                        'type: %s', alg_type)
        return None
