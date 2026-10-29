#!/usr/bin/env python3
"""Compute interpolations of input data.
"""

import logging
import bisect

from math import degrees, radians, sin, cos, asin, atan2, exp, isnan, sqrt
from statistics import mean, median, stdev
from typing import Union, Any


from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.derived_data_transform import DerivedDataTransform  # noqa: E402


################################################################################
class InterpolationTransform(DerivedDataTransform):
    """Transform that computes interpolations of the specified variables.
    """

    def __init__(self, field_spec, interval, window,
                 data_id=None, metadata_interval=None, **kwargs):
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

               Any other keys in a list entry, such as min_count, are passed
               to the algorithm along with its window.

               Algorithms:

                 boxcar_average - mean of the values within the window,
                       centred on the output time
                 polar_average - mean direction of angles (in degrees)
                       within the window, so that 359 and 1 average to 0
                 nearest - the value nearest the output time
                 median - median of the values within the window; unlike a
                       mean, unaffected by a few spikes or dropouts
                 trimmed_mean - mean of the values within the window after
                       dropping the highest and lowest; the option 'trim'
                       (default 0.1) is the fraction dropped from each end
                 time_weighted_average - mean of the values within the window,
                       each weighted by the time it covers (integrating
                       linearly between readings), so that a burst of
                       readings, or a gap, doesn't skew the mean as it does a
                       boxcar_average's. Readings are joined across a gap
                       left by missing values.
                 gaussian_average - values within the window weighted by
                       exp(-dt**2 / 2 sigma**2), dt being their distance from
                       the output time. Smoother than a boxcar, and doesn't
                       jump as a value enters or leaves the window. The option
                       'sigma' defaults to a sixth of the window, so that the
                       window spans 3 sigma either side
                 triangular_average - values within the window weighted from
                       1 at the output time down to 0 at the window's edges;
                       much like gaussian_average, and simpler
                 exponential_average - an exponential moving average, with
                       the option 'time_constant' (in seconds, required): each
                       new value moves the average by 1 - exp(-dt /
                       time_constant) of the way towards it, dt being the time
                       since the previous value. Unlike the other algorithms
                       it uses only values up to the output time, and remembers
                       the average from one output to the next, so its time
                       constant can be longer than the window. Outputs are
                       still delayed by half the transform's window, as all
                       outputs are, so for a live display give it a transform
                       of its own with a short window - but no shorter than
                       twice the interval, or values may be discarded before
                       it sees them. No value is output once the field's
                       latest value is more than a window old.

               Window statistics, for quality control. Each is an algorithm
               of its own, so to output several statistics of a field, list
               it once for each, with a different result_prefix:
                 min, max - smallest and largest value within the window.
                       max of a short-term average gives wind gusts: the
                       WMO gust is the maximum 3-second average, i.e. max
                       over the output of a 3-second boxcar_average
                 std_dev - sample standard deviation of the values within
                       the window; needs at least two values
                 circular_std_dev - standard deviation of angles (in
                       degrees) within the window, by the Yamartino method,
                       so that values either side of 0/360 are close together
                 count - how many valid values the window holds; 0, rather
                       than no value, when it holds none

               Missing values - None, or NaN as some instruments report when
               they have no reading - are ignored by all of them, so one
               missing reading doesn't make a whole average NaN. If a window
               holds nothing but missing values, no value is output for it.

               Every algorithm but nearest, count and exponential_average
               also takes an optional
               min_count (default 1): output no value for a window that holds
               fewer than this many valid values, rather than reporting an
               average of one or two readings as if the window were full.

               boxcar_average, median, trimmed_mean, min, max and std_dev
               also take an optional outlier_mads: before averaging, drop values more than this many
               median absolute deviations (MADs) from the window's median.
               It must be at least 1, so that at least half the window is
               always kept; 3 is a common choice. If more than half the values in a window
               are identical, the MAD is zero and any value that differs from
               them is dropped. min_count counts values before outliers are
               dropped.

        interval - At what intervals (in seconds) should the interpolation
               be computed?

        window - Time window (in seconds) of data we should maintain
               around the computation we're going to make.

        data_id - What data id to assign to the output

        metadata_interval - how many seconds between when we attach field metadata
               to a record we send out.
        ```

        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

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
                                     f'a list; found {type(sources)}: {sources!r}')

                # Expand source list into a traditional field_spec. Keys other
                # than these (e.g. min_count) are options for the algorithm.
                algorithm = spec_instance.get('algorithm')
                window = spec_instance.get('window')
                result_prefix = spec_instance.get('result_prefix')
                options = {k: v for k, v in spec_instance.items()
                           if k not in ('sources', 'algorithm', 'window', 'result_prefix')}
                for source in sources:
                    entry = {'source': source,
                             'algorithm': {'type': algorithm, 'window': window, **options}}
                    result_field = result_prefix + source
                    self.field_spec[result_field] = entry

                # Finally, stash sources so we know what to look for
                self.source_fields.update(sources)

        else:
            raise ValueError('InterpolationTransform: field_spec must be either list '
                             f'or dict. Found {type(field_spec)}')

        for result_field, entry in self.field_spec.items():
            _check_algorithm_options(result_field, entry.get('algorithm'))

        self.interval = interval
        self.window = window
        self.data_id = data_id
        self.metadata_interval = metadata_interval

        # A dict of the cached values we're hanging onto - use sorted
        # lists of (timestamp, value) pairs
        self.cached_values = {f: [] for f in self.source_fields}

        # The next timestamp we'd like to emit. Is set the first time we
        # call transform().
        self.next_timestamp = 0
        self.earliest_timestamp = float('inf')  # Track earliest timestamp we've seen
        self.latest_timestamp = 0
        self.last_metadata_send = 0  # last time we've sent metadata

        # For each exponential_average: (timestamp of the latest value it
        # has taken in, the average then)
        self.exponential_averages = {}

    ############################
    def fields(self):
        """Which fields are we interested in to produce transformed data?"""
        return list(self.source_fields)

    ############################
    def _metadata(self):
        """Return a dict of metadata for our derived fields."""
        metadata_fields = {
            'field': {
                'description':
                    'Interpolated values of %s via %s' %
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
        """Cached the values contained in a new record, maintaining timestamp order."""
        if type(record) not in [DASRecord, dict]:
            logging.error('InterpolationTransform records must be dict or '
                          'DASRecord. Received type %s: %s', type(record), record)
            return 0

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
                    self._insert_sorted(field, ts, val)
                    logging.debug(f'adding {ts}: {field} - {val}')

            # If not list, assume DASRecord or simple field dict; add tuple
            elif timestamp:
                self._insert_sorted(field, timestamp, new_value)
                logging.debug(f'adding {timestamp}: {field} - {new_value}')
            else:
                logging.warning('Interpolation found no timestamp in '
                                'record: %s', record)

        # Update our tracking of the earliest and latest timestamps we've seen
        self.earliest_timestamp = min(self.earliest_timestamp, timestamp)
        self.latest_timestamp = max(self.latest_timestamp, timestamp)

        # Return the timestamp of the record
        return timestamp

    ############################
    def _insert_sorted(self, field: str, timestamp: float, value: Any) -> None:
        """Insert a (timestamp, value) pair into the sorted cached values for a field."""
        cache = self.cached_values[field]

        # Use binary search to find insertion position to maintain sorted order
        timestamps = [ts for ts, _ in cache]
        pos = bisect.bisect_left(timestamps, timestamp)

        # Insert at correct position to maintain sort order
        cache.insert(pos, (timestamp, value))

    ############################
    def _clean_cache(self):
        """Remove values from cache that are too old to be useful."""
        for field in self.source_fields:
            # Iterate forward through field cache until we find a timestamp
            # that is recent enough to keep
            cache = self.cached_values[field]
            lower_limit = self.next_timestamp - self.window / 2
            keep_index = 0
            while keep_index < len(cache) and cache[keep_index][0] < lower_limit:
                keep_index += 1

            # Throw away everything before that index
            self.cached_values[field] = cache[keep_index:]

    ############################
    def _exponential_average(self, result_field, algorithm, values, timestamp):
        """Bring result_field's exponential moving average up to timestamp,
        taking in the values since the latest it has taken in, and return it
        - or None if there is no recent value."""
        latest, average = self.exponential_averages.get(result_field, (None, None))
        time_constant = algorithm['time_constant']
        try:
            for ts, val in values:
                if ts > timestamp:
                    break
                if _is_missing(val) or (latest is not None and ts <= latest):
                    continue
                if average is None:
                    average = val
                else:
                    average += (1 - exp(-(ts - latest) / time_constant)) * (val - average)
                latest = ts
        except TypeError:
            logging.error('Non-numeric value in interpolation list: %s', values)
            return None
        self.exponential_averages[result_field] = (latest, average)

        # Don't go on reporting the average of a field that has stopped
        if latest is None or timestamp - latest > (algorithm.get('window') or self.window):
            return None
        return average

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
        if not self.can_process_record(record):  # inherited from BaseModule()
            return self.digest_record(record)  # inherited from BaseModule()

        # Add the record
        self._add_record(record)

        # First time through, our 'next_timestamp' will be zero. Set it to
        # a good starting place.
        if not self.next_timestamp:
            self.next_timestamp = self.earliest_timestamp

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
        while self.next_timestamp < self.latest_timestamp - self.window / 2:
            # Clean out old data
            self._clean_cache()

            result = {}
            for result_field, entry in self.field_spec.items():
                source = entry.get('source')
                source_values = self.cached_values.get(source)
                algorithm = entry.get('algorithm')
                # logging.warning('%s->%s: %d values',
                #                source, result_field, len(source_values))
                if algorithm.get('type') == 'exponential_average':
                    value = self._exponential_average(result_field, algorithm,
                                                      source_values, self.next_timestamp)
                else:
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


# Algorithms that take the outlier_mads option
OUTLIER_ALGORITHMS = ('boxcar_average', 'median', 'trimmed_mean', 'min', 'max', 'std_dev')

# Window statistics, each its own algorithm
WINDOW_STATISTICS = ('min', 'max', 'std_dev', 'circular_std_dev', 'count')


############################
def _check_algorithm_options(result_field, algorithm):
    """Raise ValueError if an algorithm is given an option it can't use, or
    an invalid value for one."""
    if not isinstance(algorithm, dict):
        return
    alg_type = algorithm.get('type')

    outlier_mads = algorithm.get('outlier_mads')
    if outlier_mads is not None:
        if alg_type not in OUTLIER_ALGORITHMS:
            raise ValueError(f'InterpolationTransform: {result_field}: outlier_mads '
                             f'can be used with {", ".join(OUTLIER_ALGORITHMS)}, '
                             f'not {alg_type}')
        # At least 1, so that at least half of each window is always kept:
        # by definition, half the values are within one MAD of the median.
        if not isinstance(outlier_mads, (int, float)) or outlier_mads < 1:
            raise ValueError(f'InterpolationTransform: {result_field}: outlier_mads '
                             f'must be a number no less than 1; found {outlier_mads!r}')

    # count reports however many values there are, and an exponential
    # average carries on from one output to the next: a minimum makes no
    # sense for either
    if alg_type in ('count', 'exponential_average') and \
            algorithm.get('min_count') is not None:
        raise ValueError(f'InterpolationTransform: {result_field}: min_count '
                         f'can not be used with {alg_type}')

    for option, option_alg_type in (('sigma', 'gaussian_average'),
                                    ('time_constant', 'exponential_average')):
        value = algorithm.get(option)
        if value is None:
            if option == 'time_constant' and alg_type == option_alg_type:
                raise ValueError(f'InterpolationTransform: {result_field}: '
                                 f'exponential_average needs a time_constant')
            continue
        if alg_type != option_alg_type:
            raise ValueError(f'InterpolationTransform: {result_field}: {option} can '
                             f'only be used with {option_alg_type}, not {alg_type}')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f'InterpolationTransform: {result_field}: {option} must '
                             f'be a number greater than 0; found {value!r}')

    trim = algorithm.get('trim')
    if trim is not None:
        if alg_type != 'trimmed_mean':
            raise ValueError(f'InterpolationTransform: {result_field}: trim can '
                             f'only be used with trimmed_mean, not {alg_type}')
        if not isinstance(trim, (int, float)) or not 0 <= trim < 0.5:
            raise ValueError(f'InterpolationTransform: {result_field}: trim must '
                             f'be at least 0 and less than 0.5; found {trim!r}')


############################
def _reject_outliers(vals, outlier_mads):
    """Drop values more than outlier_mads median absolute deviations from
    the median. If the MAD is zero, drop every value not equal to the median."""
    center = median(vals)
    deviations = [abs(val - center) for val in vals]
    mad = median(deviations)
    return [val for val, deviation in zip(vals, deviations)
            if deviation <= outlier_mads * mad]


############################
def _circular_std_dev(angles):
    """Standard deviation of angles in degrees, by the Yamartino method:
    from how far the mean of their unit vectors falls short of length 1."""
    val_radians = [radians(val) for val in angles]
    sin_mean = mean([sin(val) for val in val_radians])
    cos_mean = mean([cos(val) for val in val_radians])
    # max() because rounding can take 1 - (length squared) just below zero
    epsilon = sqrt(max(0.0, 1 - (sin_mean ** 2 + cos_mean ** 2)))
    return degrees(asin(epsilon) * (1 + (2 / sqrt(3) - 1) * epsilon ** 3))


############################
def _is_missing(value):
    """Is this a missing value: None, or a NaN?"""
    return value is None or (isinstance(value, float) and isnan(value))


############################
def interpolate(algorithm, values, timestamp, now):
    """An omnibus routine for taking a list of timestamped values, a
    specification of an averaging algorithm, and returning a value
    computed at the specified timestamp. Returns None if there aren't
    enough data to compute a value.

    algorithm    A dict specifying the algorithm to be used: its 'type', and
                 options such as 'window' and 'min_count'

                 Missing values (None or NaN) are ignored by every algorithm.

    values       A list of [(timestamp, value),...] pairs

    timestamp    The timestamp for which interpolation should be computed

    now          Timestamp now. This should be used to determine whether
                 we're far enough beyond our timestamp to compute a value.
    """
    if not type(algorithm) is dict:
        logging.warning('Function interpolate() handed non-dict algorithm '
                        'specification: %s', algorithm)
        return None
    # Ignore missing values: None, or NaN as some instruments send when
    # they have no reading. Otherwise one of them would make a whole
    # average NaN, or be returned as the nearest value.
    values = [(ts, val) for ts, val in values if not _is_missing(val)]
    if not values:
        logging.debug('Function interpolate() has no values to work with')
        # An empty window is exactly what count is there to report
        return 0 if algorithm.get('type') == 'count' else None

    ##################
    # Select algorithm
    alg_type = algorithm.get('type')
    min_count = algorithm.get('min_count') or 1

    # boxcar_average: all values within symmetric interval window get
    # same weight.
    if alg_type == 'boxcar_average':
        window = algorithm.get('window', 10)  # How far back/forward to average
        lower_limit = timestamp - window / 2
        upper_limit = timestamp + window / 2
        vals_to_average = [val for ts, val in values
                           if ts >= lower_limit and ts <= upper_limit]
        if len(vals_to_average) < min_count:
            return None

        try:
            outlier_mads = algorithm.get('outlier_mads')
            if outlier_mads:
                vals_to_average = _reject_outliers(vals_to_average, outlier_mads)
                if not vals_to_average:
                    return None
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
        lower_limit = timestamp - window / 2
        upper_limit = timestamp + window / 2
        vals_to_average = [val for ts, val in values
                           if ts >= lower_limit and ts <= upper_limit]
        if len(vals_to_average) < min_count:
            return None

        try:
            val_radians = [radians(val) for val in vals_to_average]
            x_mean = mean([sin(val) for val in val_radians])
            y_mean = mean([cos(val) for val in val_radians])
            angle = degrees(atan2(x_mean, y_mean))
            if angle < 0:
                angle += 360
            # A tiny negative angle (rounding error when angles cancel
            # around north) plus 360 rounds to exactly 360.0
            if angle >= 360:
                angle -= 360
            return angle
        except TypeError:
            logging.error('Non-numeric value in interpolation list: %s', vals_to_average)
            return None

    # median and trimmed_mean: robust to a few spikes or dropouts.
    if alg_type in ('median', 'trimmed_mean'):
        window = algorithm.get('window', 10)  # How far back/forward to look
        lower_limit = timestamp - window / 2
        upper_limit = timestamp + window / 2
        vals_to_average = [val for ts, val in values
                           if ts >= lower_limit and ts <= upper_limit]
        if len(vals_to_average) < min_count:
            return None

        try:
            outlier_mads = algorithm.get('outlier_mads')
            if outlier_mads:
                vals_to_average = _reject_outliers(vals_to_average, outlier_mads)
                if not vals_to_average:
                    return None
            if alg_type == 'median':
                return median(vals_to_average)

            vals_to_average = sorted(vals_to_average)
            drop = int(len(vals_to_average) * algorithm.get('trim', 0.1))
            if drop:
                vals_to_average = vals_to_average[drop:-drop]
            return mean(vals_to_average)
        except TypeError:
            logging.error('Non-numeric value in interpolation list: %s', vals_to_average)
            return None

    # time_weighted_average: integrate linearly between readings (the
    # trapezoidal rule) and divide by the time they span, so each value
    # counts for the time it covers rather than once.
    if alg_type == 'time_weighted_average':
        window = algorithm.get('window', 10)  # How far back/forward to average
        lower_limit = timestamp - window / 2
        upper_limit = timestamp + window / 2
        in_window = [(ts, val) for ts, val in values
                     if ts >= lower_limit and ts <= upper_limit]
        if len(in_window) < min_count:
            return None

        try:
            span = in_window[-1][0] - in_window[0][0]
            if not span:  # all at one time, so no time to weight them by
                return mean([val for ts, val in in_window])
            area = sum((ts_1 - ts_0) * (val_0 + val_1) / 2
                       for (ts_0, val_0), (ts_1, val_1) in zip(in_window, in_window[1:]))
            return area / span
        except TypeError:
            logging.error('Non-numeric value in interpolation list: %s', in_window)
            return None

    # gaussian_average and triangular_average: weight values by their
    # distance from the output time.
    if alg_type in ('gaussian_average', 'triangular_average'):
        window = algorithm.get('window', 10)  # How far back/forward to average
        lower_limit = timestamp - window / 2
        upper_limit = timestamp + window / 2
        in_window = [(ts, val) for ts, val in values
                     if ts >= lower_limit and ts <= upper_limit]
        if len(in_window) < min_count:
            return None

        if alg_type == 'gaussian_average':
            sigma = algorithm.get('sigma') or window / 6
            weights = [exp(-(ts - timestamp) ** 2 / (2 * sigma ** 2))
                       for ts, val in in_window]
        else:
            weights = [1 - abs(ts - timestamp) / (window / 2) for ts, val in in_window]
        total_weight = sum(weights)
        if not total_weight:  # e.g. a triangle's only values at its very edges
            return None
        try:
            return sum(weight * val for weight, (ts, val)
                       in zip(weights, in_window)) / total_weight
        except TypeError:
            logging.error('Non-numeric value in interpolation list: %s', in_window)
            return None

    # Window statistics, for quality control
    if alg_type in WINDOW_STATISTICS:
        window = algorithm.get('window', 10)  # How far back/forward to look
        lower_limit = timestamp - window / 2
        upper_limit = timestamp + window / 2
        vals_in_window = [val for ts, val in values
                          if ts >= lower_limit and ts <= upper_limit]
        if alg_type == 'count':
            return len(vals_in_window)
        if len(vals_in_window) < min_count:
            return None

        try:
            outlier_mads = algorithm.get('outlier_mads')
            if outlier_mads:
                vals_in_window = _reject_outliers(vals_in_window, outlier_mads)
                if not vals_in_window:
                    return None
            if alg_type == 'min':
                return min(vals_in_window)
            if alg_type == 'max':
                return max(vals_in_window)
            if alg_type == 'std_dev':
                return stdev(vals_in_window) if len(vals_in_window) > 1 else None
            return _circular_std_dev(vals_in_window)
        except TypeError:
            logging.error('Non-numeric value in interpolation list: %s', vals_in_window)
            return None

    # Not an algorithm we recognize
    else:
        logging.warning('Function interpolate() received unrecognized algorithm '
                        'type: %s', alg_type)
        return None
