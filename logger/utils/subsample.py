#!/usr/bin/env python3
"""
"""
import logging


def subsample(algorithm, values, latest_timestamp, now):
    """An omnibus routine for taking a list of timestamped values, a
    specification of an averaging algorithm, and returning a list of
    zero, one or more timestamped "averaged" output values.

    algorithm    The name of the algorithm to be used

    values       List of values to be averaged in format of
                 [(timestamp, value), (timestamp, value),...]

    latest_timestamp
                 Timestamp of the last value that was output

    now          Timestamp now
    """
    if not isinstance(algorithm, dict):
        logging.warning('Function subsample() handed non-dict algorithm '
                        'specification: %s', algorithm)
        return None
    if not values:
        logging.info('Function subsample() handed empty values list')
        return None

    alg_type = algorithm.get('type', None)

    ##################
    # Select algorithm

    # boxcar_average: all values within symmetric interval window get
    # same weight.
    if alg_type == 'boxcar_average':
        interval = algorithm.get('interval', 10)  # How often to output
        window = algorithm.get('window', 10)     # How far back to average

        # Which timestamps are we going to emit as averages? Start at
        # 'interval' seconds after the last timestamp we emitted and end
        # at 'window/2' seconds before now, because we want to have a full
        # 'window' seconds available for most recent point.
        ts = max(latest_timestamp + interval, values[0][0] + window / 2)
        ts_list = []
        while ts <= now - window / 2:
            ts_list.append(ts)
            ts += interval

        if not ts_list:
            logging.debug('No timestamps to emit this time')
            return None

        # Start and end intervals for data for each timestamp
        ts_start = {ts: (ts - window / 2) for ts in ts_list}
        ts_end = {ts: (ts + window / 2) for ts in ts_list}
        ts_data = {ts: [] for ts in ts_list}

        # Iterate through values backwards until we're outside the window
        # of the first output ts.
        earliest_ts_of_interest = ts_list[0] - window / 2
        for v_index in range(len(values) - 1, -1, -1):
            (value_ts, value) = values[v_index]
            if value_ts < earliest_ts_of_interest:
                break

            # Does this ts,value pair belong in any of our averages?
            for ts in ts_list:
                if value_ts > ts_start[ts] and value_ts < ts_end[ts]:
                    ts_data[ts].append(value)

        # Assemble averages for all timestamps we're going to emit
        results = []
        for ts in ts_list:
            if type(ts) not in [int, float, bool]:
                logging.warning('Trying to subsample non-numeric value "%s"', ts)
                continue
            if len(ts_data[ts]):
                try:
                    results.append((ts, sum(ts_data[ts]) / len(ts_data[ts])))
                except TypeError:
                    logging.warning('Non-numeric input in subsample: %s, in %s, list: %s',
                                    ts_data[ts], ts_data, ts_list)

        return results

    else:
        logging.warning('Function subsample() received unrecognized algorithm '
                        'type: %s', alg_type)
        return None
