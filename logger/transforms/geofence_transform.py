#!/usr/bin/env python3
"""Read lat/lon from passed records and compare to a geofence loaded at initialization
time. Emit pre-defined messages if lat/lon transition between inside and outside of
fence.

EEZ files in GML format can be downloaded from https://marineregions.org/eezsearch.php

Sample logger that switches modes when entering/exiting EEZ:
```
# Read parsed DASRecords from UDP
readers:
  class: UDPReader
  kwargs:
    port: 6224
# Look for lat/lon values in the DASRecords and emit appropriate commands
# when entering/leaving EEZ. Note that EEZ files in GML format can be
# downloaded from https://marineregions.org/eezsearch.php.
transforms:
  - class: GeofenceTransform
    module: loggers.transforms.geofence_transform
    kwargs:
      latitude_field_name: s330Latitude,
      longitude_field_name: s330Longitude
      boundary_file_name: /tmp/eez.gml
      leaving_boundary_message: set_active_mode write+influx
      entering_boundary_message: set_active_mode no_write+influx
# Send the messages that we get from geofence to the LoggerManager
writers:
  - class: LoggerManagerWriter
    module: logger.writers.logger_manager_writer
    kwargs:
      database: django
      allowed_prefixes:
        - 'set_active_mode '
        - 'sleep '
```
Some questions:
- Should messages be emitted when first record is received? That is, when transform
  first fires up, should it send the "entering_boundary_message" if the first record
  it receives indicates it's inside? DECISION: Yes.

NOTE: optional parameter distance_from_boundary is in degrees. Computing the appropriate
value in km/nm is nontrivial and requires figuring out the right UTM projection for each
location and recomputing it for each point and switching when lat/lon moved to a new UTM
projection area, possibly resulting in discontinuities. Simpler and less error-prone
to just require degrees.
"""
import logging
import sys
import time

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402

# Load the transform-specific packages we need
import_errors = False
try:
    import geopandas
except ImportError:
    import_errors = True
try:
    from shapely.geometry import Point
except ImportError:
    import_errors = True


################################################################################
class GeofenceTransform():
    """Class that reads lat/lon from passed records and compare to a geofence loaded at
    initialization time. Emit pre-defined messages if lat/lon transition between inside
    and outside of fence.
    """
    def __init__(self,
                 latitude_field_name,
                 longitude_field_name,
                 boundary_file_name,
                 distance_from_boundary_in_degrees=0,
                 leaving_boundary_message=None,
                 entering_boundary_message=None,
                 seconds_between_checks=0):
        """
        ```
        latitude_field_name
        longitude_field_name
                Field names to read for lat/lon values.# what fields to listen
                to for lat/lon values. Format is assumed to be decimal, with
                negative values representing south latitude and west longitude.

        boundary_file_name
                Path to file from which to load GML boundary definition..

        distance_from_boundary_in_degrees
                Optional distance from boundary to place the fence, in degrees.
                Negative means inside the boundary.

        leaving_boundary_message
                Optional message to emit when boundary is crossed, outbound
        entering_boundary_message,
                Optional message to emit when boundary is crossed, inbound

        seconds_between_checks
                Optional number of seconds to wait between doing checks,
                computation overhead
        ```
        """
        # Only throw this error if user tries to actually use this code
        if import_errors:
            raise ImportError('GeofenceTransform requires installation of geopandas and '
                              'shapely packages. Please run "pip install geopandas shapely" '
                              'and retry.')

        self.latitude_field_name = latitude_field_name
        self.longitude_field_name = longitude_field_name
        self.leaving_boundary_message = leaving_boundary_message
        self.entering_boundary_message = entering_boundary_message
        self.seconds_between_checks = seconds_between_checks

        # Once we start receiving data, this will either be True or False
        self.last_position_inside = None

        self.last_check = 0  # timestamp: the last time we checked

        # Load the EEZ data from the GML file
        eez_data = geopandas.read_file(boundary_file_name)

        # Buffer the country's EEZ by distance in degrees
        self.buffered_eez = eez_data.buffer(distance_from_boundary_in_degrees)

    ############################
    def _get_lat_lon(self, record):
        """If the DASRecord or dict contains a lat/lon pair, return it as a tuple,
        otherwise return (None, None)."""

        if type(record) is dict:
            # Is it a simple dict with lat/lon defined at the top level?
            lat = record.get(self.latitude_field_name, None)
            lon = record.get(self.longitude_field_name, None)
            if lat is not None and lon is not None:
                return (lat, lon)

            # Is it a dict with a 'fields' subdict?
            if record.get('fields') is not None:
                lat = record['fields'].get(self.latitude_field_name, None)
                lon = record['fields'].get(self.longitude_field_name, None)
                if lat is not None and lon is not None:
                    return (lat, lon)

            # No lat/lon pairs we can find in this dict
            return (None, None)

        # Maybe they've passed us a DASRecord
        if type(record) is DASRecord:
            lat = record.fields.get(self.latitude_field_name, None)
            lon = record.fields.get(self.longitude_field_name, None)
            if lat is not None and lon is not None:
                return (lat, lon)
            else:
                return (None, None)

    # Define a function to check if a point is within N nautical miles of the geofenced area
    def _is_inside_boundary(self, lat, lon):
        # Note that Point() takes longitude as first arg, not latitude
        point = Point(lon, lat)
        return self.buffered_eez.contains(point).any()

    ############################
    def transform(self, record):
        """Look for the named lat/lon fields in the passed dict. If the previous
        lat/lon pair was on one side of the geofence and this lat/lon pair is on
        the other, return the appropriate string defined in either
        leaving_boundary_message or entering_boundary_message. Otherwise, return
        None.

        record
                A DASRecord, dict of {field_name: field_value} pairs, or a list of
                DASRecords/dicts in which to look for the specified latitude_field_name
                and longitude_field_name.
        """
        if record is None:
            return None

        # If we've checked too recently, skip check. Note that because this decision
        # is made for computational efficiency rather than data efficiency, it is made
        # based on system time, not the timestamp of the record.
        now = time.time()
        time_since_last = now - self.last_check
        if self.seconds_between_checks and time_since_last < self.seconds_between_checks:
            logging.debug(f'Only {time_since_last} seconds since last GeofenceTransform check; '
                          f'less than the {self.seconds_between_checks} required.')
            return None

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list.
        if type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record))
            return results

        # Does this record have a lat/lon?
        (lat, lon) = self._get_lat_lon(record)
        if lat is None or lon is None:
            return None

        # We have a lat and lon, so we're going ahead and checking
        self.last_check = now

        is_inside = self._is_inside_boundary(lat, lon)
        if is_inside == self.last_position_inside:
            return None

        self.last_position_inside = is_inside
        if is_inside:
            return self.entering_boundary_message
        else:
            return self.leaving_boundary_message
