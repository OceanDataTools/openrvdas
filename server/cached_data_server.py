#!/usr/bin/env python3

"""Accept data in DASRecord or dict format via the cache_record() method,
then serve it to anyone who connects via a websocket. A
CachedDataServer can be instantiated by running this script from the
command line and providing one or more UDP ports on which to listen
for timestamped text data that it can parse into key:value pairs. It
may also be instantiated as part of a CachedDataWriter that can be
invoked on the command line via the listen.py script of via a
configuration file.
The following direct invocation of this script
```
    logger/utils/cached_data_server.py \
      --udp 6225 \
      --port 8766 \
      --disk_cache /var/tmp/openrvdas/disk_cache \
      --back_seconds 3600 \
      --v
```
says to
1. Listen on the UDP port specified by --udp for JSON-encoded,
   timestamped, field:value pairs. (See the definition for cache_record(),
   below for formats understood.)
2. Store the received data in memory, retaining the most recent 3600
   seconds for each field (default is 86400 seconds = 24 hours).
   (The total number of values cached per field is also limited by the
   ``max_records`` parameter and defaults to 2880, equivalent to two
   records per minute for 24 hours. It may be overridden to "infinite"
   by setting ``--max_records=0`` on the command line.)
3. Periodically back up the in-memory cache to a disk-based cache at
   /var/tmp/openrvdas/disk_cache (By default, back up every 60 seconds;
   this can be overridden with the --cleanup_interval argument).
4. Wait for clients to connect to the websocket at port 8766 and serve
   them the requested data. Web clients may issue JSON-encoded
   requests of the following formats (see the definition of
   serve_requests() for insight):
```
   {'type':'fields'}   - return a list of fields for which cache has data
   {'type':'describe',
    'fields':['field_1', 'field_2', 'field_3']}
       - return a dict of metadata descriptions for each specified field. If
         'fields' is omitted, return a dict of metadata for *all* fields
   {'type':'subscribe',
    'fields':{'field_1':{'seconds':50},
              'field_2':{'seconds':0, 'back_records':10},
              'field_3':{'seconds':-1}}}
       - subscribe to updates for field_1, field_2 and field_3. Allowable
         values for 'seconds':
            0  - provide only new values that arrive after subscription
           -1  - provide the most recent value, and then all future new ones
           num - provide num seconds of back data, then all future new ones
         If 'seconds' is missing, use '0' as the default.

         If 'back_records' is present it must be a number greater than or equal
         to zero. If present and non-zero, the CDS will try to provide at least
         that many "back records" when it first returns, even if it has to go
         back further than the interval specified in 'seconds'.
   {'type':'ready'}
       - indicate that client is ready to receive the next set of updates
         for subscribed fields.
   {'type':'publish', 'data':{'timestamp':1555468528.452,
                              'fields':{'field_1':'value_1',
                                        'field_2':'value_2'}}}
       - submit new data to the cache (an alternative way to get data
         in without the same record size limits of a UDP packet).
```
"""
import asyncio
import json
import logging
import os
import os.path
import re
import sys
import threading
import time
import websockets

try:
    from websockets.exceptions import ConnectionClosed
except ImportError:
    from websockets.connection import ConnectionClosed

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from logger.utils.stderr_logging import StdErrLoggingHandler  # noqa: E402
from logger.utils.das_record import DASRecord                 # noqa: E402
from logger.writers.text_file_writer import TextFileWriter    # noqa: E402


############################
class RecordCache:
    """Structure for storing/retrieving record data and metadata."""

    def __init__(self):
        """
        In-memory storage for key:value pairs.
        """
        self.data = {}
        self.data_lock = threading.Lock()  # When operating on whole dict

        self.metadata = {}
        self.metadata_lock = threading.Lock()

        # Disk files we've tried to write to but failed.
        self.failed_files = set()

        # Create a lock for each key so threads don't step on each other
        self.locks = {key: threading.Lock() for key in self.keys()}

    ############################
    def cache_record(self, record):
        """Add the passed record to the cache.
        Expects passed records to be in one of two formats:
        1) DASRecord
        2) A dict encoding optionally a source data_id and timestamp and a
           mandatory 'fields' key of field_name: value pairs. This is the format
           emitted by default by ParseTransform:
      ```
           {
             'data_id': ...,    # optional
             'timestamp': ...,  # optional - use time.time() if missing
             'fields': {
               field_name: value,
               field_name: value,
               ...
             }
           }
      ```
        A twist on format (2) is that the values may either be a singleton
        (int, float, string, etc) or a list. If the value is a singleton,
        it is taken at face value. If it is a list, it is assumed to be a
        list of (value, timestamp) tuples, in which case the top-level
        timestamp, if any, is ignored.
      ```
           {
             'data_id': ...,  # optional
             'fields': {
                field_name: [(timestamp, value), (timestamp, value),...],
                field_name: [(timestamp, value), (timestamp, value),...],
                ...
             }
           }
      ```
        In addition to a 'fields' field, a record may contain a 'metadata'
        field. If present, the data server will look for a 'fields' dict
        inside the metadata dict and add the key-value pairs there to its
        cache of metadata about the fields:
      ```
           {'data_id': 's330',
            'fields': {'S330CourseMag': 244.29,
                       'S330CourseTrue': 219.61,
                       'S330Mode': 'A',
                       'S330SpeedKm': 16.5,
                       'S330SpeedKt': 8.9},
            'metadata': {'fields': {
              'S330CourseMag': {'description': 'Magnetic course',
                                'device': 's330',
                                'device_type': 'Seapath330',
                                'device_type_field': 'CourseMag',
                                'units': 'degrees'},
              'S330CourseTrue': {'description': 'True course',
                                 ...}
              }
            }}
      ```
        This metadata field will be generated sent at intervals by a
        RecordParser (and its enclosing ParseTransform) if the parser's
        ``metadata_interval`` value is not None.
        """
        logging.debug('cache_record() received: %s', record)
        if not record:
            logging.debug('cache_record() received empty record.')
            return

        # If we've been passed a DASRecord, the field:value pairs are in a
        # field called, uh, 'fields'; if we've been passed a dict, look
        # for its 'fields' key.
        if isinstance(record, DASRecord):
            record_timestamp = record.timestamp
            fields = record.fields
            metadata = record.metadata
        elif isinstance(record, dict):
            record_timestamp = record.get('timestamp', time.time())
            fields = record.get('fields', None)
            metadata = record.get('metadata', None)
            if fields is None:
                logging.debug(
                    'Dict record passed to cache_record() has no '
                    '"fields" key, which either means it\'s not a dict '
                    'you should be passing, or it is in the old "field_dict" '
                    'format that assumes key:value pairs are at the top '
                    'level.')
                logging.debug('The record in question: %s', str(record))
                return
        else:
            logging.warning(
                'Received non-DASRecord, non-dict input (type: %s): %s',
                type(record),
                record)
            return

        # Add values from record to cache
        for field, value in fields.items():
            if field not in self.locks:
                self.locks[field] = threading.Lock()
            with self.locks[field]:
                if field not in self.data:
                    self.data[field] = []

                if isinstance(value, list):
                    # Okay, for this field we have a list of values - iterate
                    # through
                    for val in value:
                        # If element in the list is itself a list or a tuple,
                        # we'll assume it's a (timestamp, value) pair. Otherwise,
                        # use the default timestamp of 'now'.
                        if type(val) in [list, tuple]:
                            self._add_tuple(field, val)
                        else:
                            self._add_tuple(field, (record_timestamp, value))
                else:
                    # If type(value) is *not* a list, assume it's the value
                    # itself. Add it using the default timestamp.
                    self._add_tuple(field, (record_timestamp, value))

            # Is there any metadata to add? Cache whatever is in the
            # metadata.data.fields dict. Blithely overwrite whatever might
            # be there already.
            if metadata:
                metadata_fields = metadata.get('fields', {})
                with self.metadata_lock:
                    for field, value in metadata_fields.items():
                        self.metadata[field] = value

    ############################
    def _add_tuple(self, field, value_tuple):
        self.data[field].append(value_tuple)

    ############################
    def keys(self):
        """Return a list of all keys in the cache."""
        return list(self.data.keys())

    ############################
    def get_metadata(self, fields=None):
        """Return a dict of metadata for the specified list of fields. If no
        fields are specified, return metadata for all fields.
        """
        with self.metadata_lock:
            if fields:
                return {
                    field: self.metadata.get(
                        field, {}) for field in fields}
            else:
                return self.metadata

    ############################
    def cleanup(self, oldest=0, max_records=0, min_back_records=0):
        """Remove any data from cache with a timestamp older than 'oldest'
        seconds, but keep at least one (most recent) value.
        If max_records is non-zero, truncate to that many of the most
        recent records. Always, though, keep at least min_back_records.
        """
        logging.debug('Cleaning up cache')
        fields = self.keys()
        for field in fields:
            if field not in self.locks:
                self.locks[field] = threading.Lock()
            with self.locks[field]:
                value_list = self.data[field]

                if len(value_list) <= min_back_records:
                    continue

                # If max_records is specified, truncate to keep that many of
                # most recent records.
                if max_records > min_back_records and len(value_list) > max_records:
                    value_list = value_list[-max_records:]

                # Iterate until find value that's not too old, but leave at least
                # min_back_records.
                for i in range(len(value_list) - min_back_records):
                    if value_list[i][0] > oldest:
                        break

                # But keep at least one value
                last_index = min(i, len(value_list) - 1)
                self.data[field] = value_list[last_index:]

    ############################
    def save_to_disk(self, disk_cache):
        """Create one JSON-encoded cache file per field in the directory named
        by disk_cache.
        """
        logging.debug('Saving to cache.')
        if not disk_cache:
            logging.warning('save_to_disk called, but no disk_cache defined')
            return

        if not os.path.exists(disk_cache):
            try:
                os.makedirs(disk_cache)
            except OSError as e:
                logging.error('Unable to create disk cache directory "%s": %s', disk_cache, e)
                return

        fields = self.keys()
        for field in fields:
            disk_filename = disk_cache + '/' + field
            if disk_filename in self.failed_files:
                continue
            if field not in self.locks:
                self.locks[field] = threading.Lock()
            with self.locks[field]:
                try:
                    with open(disk_filename, 'w') as cache_file:
                        json.dump(self.data[field], cache_file)
                except (PermissionError, IOError, OSError) as e:
                    logging.warning('Unable to write disk cache file %s: %s', disk_filename, e)
                    self.failed_files.add(disk_filename)

                # This is BAD practice; but use it to figure out what else might go wrong
                # so we can add it to specific exceptions above.s
                except Exception as e:
                    logging.warning('Unanticipated exception writing disk cache file %s: %s',
                                    disk_filename, e)
                    self.failed_files.add(disk_filename)

    ############################
    def load_from_disk(self, disk_cache):
        """Load the data dict from directory of JSON-encoded cache files.
        """
        logging.info('Loading from disk at %s', disk_cache)
        if not disk_cache:
            logging.info('load_from_disk called, but no disk_cache defined')
            return
        try:
            if not os.path.exists(disk_cache):
                logging.info('load_from_disk: no cache found at "%s"', disk_cache)
                return

            field_files = [f for f in os.listdir(disk_cache)
                           if os.path.isfile(os.path.join(disk_cache, f))]
            logging.debug('Got cached fields: %s', field_files)
            for field in field_files:
                if field not in self.locks:
                    self.locks[field] = threading.Lock()
                try:
                    with self.locks[field]:
                        with open(disk_cache + '/' + field, 'r') as cache_file:
                            self.data[field] = json.load(cache_file)

                except (json.decoder.JSONDecodeError, UnicodeDecodeError):
                    logging.warning('Failed to parse cache for %s', field)
        except OSError as e:
            logging.error('Unable to access disk cache at %s: %s', disk_cache, e)


############################
class WebSocketConnection:
    """Handle the websocket connection, serving data as requested."""
    ############################

    def __init__(self, websocket, cache, interval):
        self.websocket = websocket
        self.cache = cache
        self.interval = interval
        self.quit_flag = False

    ############################
    def closed(self):
        """Has our client closed the connection?"""
        return self.quit_flag

    ############################
    def quit(self):
        """Close the connection from our end and quit."""
        self.quit_flag = True

    ############################
    def get_matching_field_names(self, field_name):
        """If a wildcard field is present, returns a list
        (matching_field_names) of all the fields that match the
        pattern. Otherwise, it just returns the field_name as the sole
        entry in the list.

        field_name - the name of the field as specified in the subscription request
        """

        matching_field_names = set()

        # If the field name is a wildcard
        if '*' in field_name:
            field_name = field_name.replace("*", ".+")

            for field in self.cache.keys():
                if re.search(field_name, field):
                    matching_field_names.add(field)

        # If here, the field name is not a wildcard
        else:
            matching_field_names.add(field_name)

        return list(matching_field_names)

    ############################

    async def send_json_response(self, response, is_error=False):
        logging.debug('CachedDataServer sending %d bytes',
                      len(json.dumps(response)))
        await self.websocket.send(json.dumps(response))
        if is_error:
            logging.warning(response)

    ############################
    async def serve_requests(self):
        """Wait for requests and serve data, if it exists, from
        cache. Requests are in JSON with request type encoded in
        'request_type' field. Recognized request types are:
        ```
        fields - return a (JSON encoded) list of fields for which cache
            has data.
        describe - return a (JSON encoded) dict of metadata for the listed
            fields.
        publish - look for a field called 'data' and expect its value to
            be a dict containing data in one of the formats accepted by
            cache_record().
        subscribe - look for a field called 'fields' in the request whose
            value is a dict of the format
            ```
              {field_name:{seconds:600, back_records:10},
               field_name:{seconds:0},...}
            ```
            The entire specification may also have a field called
            'interval', specifying how often server should provide
            updates. Will default to what was specified on command line
            with --interval flag (which itself defaults to 1 second
            intervals).
            ```
            ```
            A subscription will instruct the CachedDataServer to begin
            serving JSON messages of the format
            ```
              {
                field_name: [(timestamp, value), (timestamp, value),...],
                field_name: [(timestamp, value), (timestamp, value),...],
                field_name: [(timestamp, value), (timestamp, value),...],
              }
            ```
            Initially provide the number of seconds worth of back data
            requested, and on subsequent calls, return all data that have
            arrived since last call.
            NOTE: if the 'seconds' field is -1, server will only ever provide
            the single most recent value for the relevant field.
        ready - client has processed the previous data message and is ready
            for more.
        ```
        """
        # The field details specified in a subscribe request
        requested_fields = {}

        # A map from field_name:latest_timestamp_sent. If latest_timestamp_sent is -1
        # then we'll always send just the most recent value we have for the field,
        # regardless of how many there are, or whether we've sent it before.
        field_timestamps = {}

        interval = self.interval  # Use the default interval, uh, by default

        while not self.quit_flag:
            now = time.time()
            try:
                logging.debug('Waiting for client')
                raw_request = await self.websocket.recv()
                request = json.loads(raw_request)

                # Make sure we've received a dict
                if not isinstance(request, dict):
                    await self.send_json_response(
                        {'status': 400, 'error': 'non-dict request received'},
                        is_error=True)

                # Make sure request dict has a 'type' field
                elif 'type' not in request:
                    await self.send_json_response(
                        {'status': 400, 'error': 'no "type" field found in request'},
                        is_error=True)

                # Let's see what type of request it is

                # Send client a list of the variable names we're able to serve.
                elif request['type'] == 'fields':
                    logging.debug('fields request')
                    await self.send_json_response(
                        {'type': 'fields', 'status': 200,
                         'data': self.cache.keys()})

                # Send client a dict of metadata descriptions; if they've
                # specified a set of fields, give just metadata for those;
                # otherwise send everything.
                elif request['type'] == 'describe':
                    logging.debug('describe request')
                    fields = request.get('fields', None)
                    result = self.cache.get_metadata(fields)
                    await self.send_json_response(
                        {'type': 'describe', 'status': 200, 'data': result})

                # Client wants to publish to cache and provides a dict of data
                elif request['type'] == 'publish':
                    logging.debug('publish request')
                    data = request.get('data', None)
                    if data is None:
                        await self.send_json_response(
                            {'type': 'publish', 'status': 400,
                             'error': 'no data field found in request'},
                            is_error=True)
                    elif not isinstance(data, dict):
                        await self.send_json_response(
                            {'type': 'publish', 'status': 400,
                             'error': 'request has non-dict data field'},
                            is_error=True)
                    else:
                        self.cache.cache_record(data)
                        await self.send_json_response({'type': 'publish', 'status': 200})

                # Client wants to subscribe, and provides a dict of requested
                # fields
                elif request['type'] == 'subscribe':
                    logging.debug('subscribe request')
                    # Have they given us a new subscription interval?
                    requested_interval = request.get('interval', None)
                    if requested_interval is not None:
                        try:
                            interval = float(requested_interval)
                        except ValueError:
                            await self.send_json_response(
                                {'type': 'subscribe', 'status': 400,
                                 'error': 'non-numeric interval requested'},
                                is_error=True)
                            continue

                    # Which fields do they want?
                    raw_requested_fields = request.get('fields', None)
                    if not raw_requested_fields:
                        await self.send_json_response(
                            {'type': 'subscribe', 'status': 400,
                             'error': 'no fields found in subscribe request'},
                            is_error=True)
                        continue

                    # What format do they want output in? field_dict?
                    # record_list? By default, use field_dict.
                    requested_format = request.get('format', 'field_dict')

                    # Parse out request field names and number of back seconds
                    # requested. Encode that as 'last timestamp sent', unless back
                    # seconds == -1. If -1, save it as -1, so that we know we're
                    # always just sending the the most recent field value. Stores
                    # all fields, including expanded entries from a wildcard, in the
                    # requested_fields dict.

                    now = time.time()

                    # Reset requested field_timestamps and field_back_records
                    requested_fields = {}
                    field_timestamps = {}    # last timestamp seen

                    logging.debug('Subscription requested')
                    for field_name, field_spec in raw_requested_fields.items():
                        matching_field_names = self.get_matching_field_names(field_name)

                        for matching_field_name in matching_field_names:
                            requested_fields[matching_field_name] = field_spec
                            # If we don't have a field spec dict
                            if isinstance(field_spec, dict):
                                back_records = field_spec.get('back_records', 0)
                                back_seconds = field_spec.get('seconds', 0)
                            else:
                                back_records = 0
                                back_seconds = 0

                            # Now figure out what's the latest timestamp we have for this
                            # field name that respects the back_records and back_seconds
                            # specification.
                            field_timestamps[matching_field_name] = 0  # if nothing else

                            if field_name not in self.cache.locks:
                                logging.debug('No data for requested field %s', matching_field_name)
                                continue
                            with self.cache.locks[field_name]:
                                field_cache = self.cache.data.get(matching_field_name, None)
                                if field_cache is None:
                                    logging.debug('No cached data for %s', matching_field_name)
                                    continue

                                logging.debug('    %s: %d records available; %d requested, '
                                              '%d seconds', matching_field_name, len(field_cache),
                                              back_records, back_seconds)
                                # If no data for requested field, skip.
                                if not field_cache or not field_cache[-1]:
                                    continue

                                # If special case 0, they only want records that come after
                                # this point in time. Set the  last timestamp seen as the
                                # most-recently seen timestamp, or zero if no entries.
                                if back_seconds == 0:
                                    if len(field_cache) > 0:
                                        field_timestamps[matching_field_name] = field_cache[-1][0]
                                    else:
                                        field_timestamps[matching_field_name] = 0
                                    continue

                                # If special case -1, they want just single most recent
                                # value. Set the last timestamp seen as the second to last
                                # timestamp if multiple entries, or as zero, if only 1.
                                if back_seconds == -1:
                                    if len(field_cache) > 1:
                                        field_timestamps[matching_field_name] = field_cache[-2][0]
                                    else:
                                        field_timestamps[matching_field_name] = 0
                                    continue

                                # We've been told to return at least 'back_records' records; if
                                # there aren't at least that many, leave field_timestamps[field]
                                # at zero to return all we've got.
                                if len(field_cache) <= back_records:
                                    continue

                                # If here, we've got at least 'back_records' records, and want to
                                # search backward to include the last 'back_seconds' seconds of
                                # them. Could do more efficiently with some sort of binary search.
                                this_record_index = len(field_cache) - back_records - 1
                                while this_record_index >= 0:
                                    # Recall that each element is (timestamp, value)
                                    this_timestamp = field_cache[this_record_index][0]

                                    if now - this_timestamp > back_seconds:
                                        # Set our 'last seen' timestamp as timestamp of previous
                                        # record and stop looking.
                                        prev_timestamp = field_cache[this_record_index-1][0]
                                        field_timestamps[matching_field_name] = prev_timestamp
                                        break
                                    this_record_index -= 1

                    if raw_requested_fields and not requested_fields:
                        logging.info('Request doesn\'t match any existing fields')

                    # Let client know request succeeded
                    await self.send_json_response({'type': 'subscribe', 'status': 200})

                # Client just letting us know it's ready for more. If there are
                # fields that have been requested, send along any new data for
                # them.
                elif request['type'] == 'ready':
                    logging.debug('Websocket got ready...')
                    if not field_timestamps:
                        # Client has told us that they're ready, but there are no
                        # fields that match their request. Let them know, then
                        # pause a moment before we try fielding their next
                        # request.
                        await self.send_json_response(
                            {'type': 'ready', 'status': 400,
                             'error': 'client ready, but no matching fields found (yet).'},
                            is_error=False)
                        await asyncio.sleep(self.interval * 5)

                    ##########
                    results = {}
                    if requested_format == 'field_dict':
                        for field_name, field_spec in requested_fields.items():
                            if field_name not in self.cache.locks:
                                logging.debug('No data for requested field %s', field_name)
                                continue

                            with self.cache.locks[field_name]:
                                field_cache = self.cache.data.get(field_name, None)
                                if field_cache is None:
                                    logging.debug(
                                        'No cached data for %s', field_name)
                                    continue

                                # If no data for requested field, skip.
                                if not field_cache or not field_cache[-1]:
                                    continue

                                # If special case -1, they want just single most recent
                                # value, then future results. Grab last value, then set its
                                # timestamp as the last one we've seen.
                                back_seconds = field_spec.get('back_seconds', 0)
                                if back_seconds == -1:
                                    last_value = field_cache[-1]
                                    results[field_name] = [last_value]
                                    # ts of last value
                                    field_timestamps[field_name] = last_value[0]
                                    continue

                                # Otherwise - if no data newer than the latest
                                # timestamp we've already sent, skip,
                                latest_timestamp = field_timestamps.get(field_name, 0)
                                if not field_cache[-1][0] > latest_timestamp:
                                    continue

                                # Otherwise, copy over records arrived since
                                # latest_timestamp and update the latest_timestamp sent
                                # (first element of last pair in field_cache).
                                field_results = [
                                    pair for pair in field_cache if pair[0] > latest_timestamp]
                                results[field_name] = field_results
                                if field_results:
                                    field_timestamps[field_name] = field_results[-1][0]

                    ##########
                    # If not outputting data as a field dict, output as a list
                    # of records.
                    elif requested_format == 'record_list':
                        records = {}
                        for field_name, field_spec in requested_fields.items():
                            if field_name not in self.cache.locks:
                                logging.debug(
                                    'No data for requested field %s', field_name)
                                continue
                            with self.cache.locks[field_name]:
                                latest_timestamp = field_timestamps.get(
                                    field_name, 0)
                                field_cache = self.cache.data.get(
                                    field_name, None)

                                if not field_cache or not field_cache[-1]:
                                    logging.debug(
                                        'No cached data for %s', field_name)
                                    continue

                                # If latest_timestamp is special case -1, they want just
                                # single most recent value, then future results. Grab
                                # last value, then set its timestamp as the last one
                                # we've seen.
                                elif latest_timestamp == -1:
                                    last_ts, last_value = field_cache[-1]
                                    if last_ts not in records:
                                        records[last_ts] = {}
                                    records[last_ts][field_name] = last_value
                                    field_timestamps[field_name] = last_ts
                                    continue

                                # Otherwise - if no data newer than the latest
                                # timestamp we've already sent, skip,
                                elif not field_cache[-1][0] > latest_timestamp:
                                    continue

                                # Otherwise, copy over records arrived since
                                # latest_timestamp and update the latest_timestamp sent
                                # (first element of last pair in field_cache).
                                else:
                                    # Get the new (ts, value) pairs for this
                                    # field
                                    field_results = [
                                        pair for pair in field_cache if pair[0] > latest_timestamp]

                                    # We know field_results is non-empty because of previous
                                    # elif, so new latest timestamp is last ts
                                    # in it.
                                    field_timestamps[field_name] = field_results[-1][0]

                                    # Collate values by timestamp, folding into values for
                                    # other fields.
                                    for ts, value in field_results:
                                        if ts not in records:
                                            records[ts] = {}
                                        records[ts][field_name] = value

                        # Create and send a list with one DASRecord-like dict for
                        # each timestamp.
                        results = [{'timestamp': ts, 'fields': records[ts]}
                                   for ts in sorted(records)]

                    # If unknown requested format
                    else:
                        mesg = (
                            'Unrecognized requested format: %s; valid formats are '
                            '"field_dict" and "record_list"' %
                            requested_format)
                        logging.warning(mesg)
                        await self.send_json_response({'status': 400, 'error': mesg}, is_error=True)

                    logging.debug(
                        'Websocket results: %s...',
                        str(results)[
                            0:100])

                    # Package up what results we have (if any) and send them
                    # off
                    await self.send_json_response({'type': 'data', 'status': 200,
                                                   'data': results})

                    # New results or not, take a nap before trying to fetch
                    # more results
                    elapsed = time.time() - now
                    time_to_sleep = max(0, interval - elapsed)
                    logging.debug('Sleeping %g seconds', time_to_sleep)
                    await asyncio.sleep(time_to_sleep)

                # If unrecognized request type - whine, then iterate
                else:
                    await self.send_json_response(
                        {'status': 400,
                         'error': 'unrecognized request type: %s' % request['type']},
                        is_error=True)

            # If we got bad input, complain and loop
            except json.JSONDecodeError:
                await self.send_json_response(
                    {'status': 400, 'error': 'received unparseable JSON'},
                    is_error=True)
                logging.warning('unparseable JSON: %s', raw_request)

            # If our connection closed, complain and exit gracefully
            except ConnectionClosed:
                logging.info('Client closed connection')
                self.quit()


##########################################################################
class CachedDataServer:
    """Class that caches field:value pairs passed to it in either a
    DASRecord or a simple dict. It also establishes a websocket server
    on the specified port and serves the cached values to clients that
    connect via a websocket.
    The server listens for two types of requests:
    1. If the request is the string "variables", return a list of the
       names of the variables the server has in cache and is able to
       serve. The server will continue listening for follow up messages,
       most likely this one:
    2. If the request is a python dict, assume it is of the form:
    ```
        {field_1_name: {'seconds': num_secs},
         field_2_name: {'seconds': num_secs},
         ...}
    ```
       where seconds is a float representing the number of seconds of
       back data being requested.
       This field dict is passed to serve_fields(), which will to retrieve
       num_secs of back data for each of the specified fields and return it
       as a JSON-encoded dict of the form:
    ```
         {
           field_1_name: [(timestamp, value), (timestamp, value), ...],
           field_2_name: [(timestamp, value), (timestamp, value), ...],
           ...
         }
    ```
    The server will then await a "ready" message from the client, and when
    received, will loop and send a JSON-encoded dict of all the
    (timestamp, value) tuples that have come in since the previous
    request. It will continue this behavior indefinitely, waiting for a
    "ready" request and sending updates.
    """

    ############################
    def __init__(
            self,
            port,
            interval=1,
            back_seconds=60 * 60,
            max_records=60 * 24,
            min_back_records=100,
            cleanup_interval=60,
            disk_cache=None,
            event_loop=None):
        """
        port         Port on which to serve websocket connections
        interval     How frequently to serve updates
        back_seconds
                     How many seconds of back data to retain
        max_records
                     Maximum number of records to store for each variable
        min_back_records
                     Minimum number of back records to keep when purging old data
        cleanup_interval
                     How many seconds between calls to cleanup old cache entries
                     and save to disk (if disk_cache is specified)
        disk_cache   If not None, name of directory in which to backup values
                     from in-memory cache
        event_loop   If not None, the event loop to use for websocket events
        """
        self.port = port
        self.interval = interval
        self.back_seconds = back_seconds
        self.max_records = max_records
        self.min_back_records = min_back_records
        self.cleanup_interval = cleanup_interval
        self.event_loop = event_loop

        self.cache = RecordCache()

        # If they've given us the name of a disk cache, try loading our
        # RecordCache from it.
        self.disk_cache = disk_cache
        if disk_cache:
            self.cache.load_from_disk(disk_cache)

        # List where we'll store our websocket connections so that we can
        # keep track of which are still open, and signal them to close
        # when we're done.
        self._connections = []
        self._connection_lock = threading.Lock()

        # If we've received an event loop, use it, otherwise create a new one
        # of our own.
        if not event_loop:
            self.event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.event_loop)
        else:
            self.event_loop = None
            asyncio.set_event_loop(event_loop)

        self.quit_flag = False

        # Start a thread to loop through, cleaning up the cache and (if we've
        # been given a disk_cache file) backing memory up to it.
        threading.Thread(target=self.cleanup_loop, daemon=True).start()

        # Fire up the thread that's going to the websocket server in our
        # event loop. Calling quit() it will close any remaining
        # connections and stop the event loop, terminating the server.
        self.server_thread = threading.Thread(
            target=self._run_websocket_server, daemon=True)
        self.server_thread.start()

    ############################
    def __del__(self):
        if self.event_loop:
            self.event_loop.stop()
            self.event_loop.close()

    ############################
    def cache_record(self, record):
        """Cache the passed record."""
        self.cache.cache_record(record)

    ############################
    def cleanup_loop(self):
        """Clear out records older than oldest seconds."""
        while not self.quit_flag:
            time.sleep(self.cleanup_interval)

            # What's the oldest record we should retain?
            oldest = time.time() - self.back_seconds
            self.cache.cleanup(oldest=oldest, max_records=self.max_records,
                               min_back_records=self.min_back_records)

            # If we're using a disk cache, save things now
            if self.disk_cache:
                self.cache.save_to_disk(self.disk_cache)

    ############################
    def _run_websocket_server(self):
        """Start serving on the specified websocket.
        """
        logging.info('Starting WebSocketServer on port %d', self.port)
        try:
            self.websocket_server = websockets.serve(
                ws_handler=self._serve_websocket_data,
                host='', port=self.port, loop=self.event_loop)

            # If event loop is already running, just add server to task list
            if self.event_loop.is_running():
                asyncio.ensure_future(
                    self.websocket_server, loop=self.event_loop)

            # Otherwise, fire up the event loop now
            else:
                self.event_loop.run_until_complete(self.websocket_server)
                self.event_loop.run_forever()
        except OSError as e:
            logging.fatal(
                'Failed to open websocket on port %s: %s',
                self.port,
                str(e))
            raise e

    ############################
    def quit(self):
        """Exit the loop and shut down all loggers.
        """
        self.quit_flag = True

        # Close any connections
        with self._connection_lock:
            for connection in self._connections:
                connection.quit()
        logging.info('WebSocketServer closed')

        # Stop the event loop that's serving connections
        self.event_loop.stop()

        # Wait for thread that's running the server to finish
        self.server_thread.join()

    ############################
    """Top-level coroutine for running CachedDataServer."""
    async def _serve_websocket_data(self, websocket, path):
        logging.debug('New data websocket client attached: %s', path)

        # Here is where we see the anomalous behavior - when constructed
        # directly, self.cache is as it should be: a shared cache. But
        # when invoked indirectly, e.g. as part of a listener via
        #
        #    listener = ListenerFromLoggerConfig(config)
        #    proc = multiprocessing.Process(target=listener.run, daemon=True)
        #    proc.start()
        #
        # then self.cache always appears ins in its initial (empty) state.
        connection = WebSocketConnection(websocket, self.cache, self.interval)

        # Stash the connection so we can tell it to exit when we receive a
        # quit(). But first do some cleanup, getting rid of old
        # connections that have closed.
        with self._connection_lock:
            index = 0
            while index < len(self._connections):
                if self._connections[index].closed():
                    logging.debug('Disposing of closed connection.')
                    self._connections.pop(index)
                else:
                    index += 1
            # Now add the new connection
            self._connections.append(connection)

        # If client disconnects, tell connection to quit
        try:
            await connection.serve_requests()
        except ConnectionClosed:
            logging.warning('client disconnected')
        except KeyboardInterrupt:
            logging.warning('Keyboard Interrupt')

        connection.quit()
        await websocket.close()


##########################################################################
##########################################################################
if __name__ == '__main__':
    import argparse

    from logger.readers.composed_reader import ComposedReader
    from logger.readers.udp_reader import UDPReader
    from logger.transforms.from_json_transform import FromJSONTransform

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', dest='port', required=True,
                        action='store', type=int,
                        help='Websocket port on which to serve data')

    parser.add_argument('--udp', dest='udp', default=None, action='store',
                        help='Comma-separated list of network ports to listen '
                        'for data on, e.g. 6221,6224. Prefix by group id '
                        'to specify multicast.')

    parser.add_argument('--disk_cache', dest='disk_cache', default=None,
                        action='store', help='If specified, periodically '
                        'backup the in-memory cache to disk. On restart, '
                        'data will be reloaded from this cache.')

    parser.add_argument('--back_seconds', dest='back_seconds', action='store',
                        type=float, default=24 * 60 * 60,
                        help='Maximum number of seconds of old data to keep '
                        'for serving to new clients.')

    parser.add_argument('--max_records', dest='max_records', action='store',
                        type=int, default=24 * 60 * 2,
                        help='Maximum number of records to store per variable.')

    parser.add_argument('--min_back_records', dest='min_back_records', action='store',
                        type=float, default=64,
                        help='Minimum number of back records to keep when purging old data.')

    parser.add_argument('--cleanup_interval', dest='cleanup_interval',
                        action='store', type=float, default=60,
                        help='How often to clean old data out of the cache.')

    parser.add_argument('--interval', dest='interval', action='store',
                        type=float, default=0.5,
                        help='How many seconds to sleep between successive '
                        'sends of data to clients.')

    parser.add_argument('--stderr_file', dest='stderr_file', default=None,
                        help='Optional file to which stderr messages should '
                        'be written.')

    parser.add_argument('-v', '--verbosity', dest='verbosity', default=0,
                        action='count', help='Increase output verbosity')
    args = parser.parse_args()

    # Set logging verbosity
    LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}

    log_level = LOG_LEVELS[min(args.verbosity, max(LOG_LEVELS))]
    logging.basicConfig(format=LOGGING_FORMAT)
    logging.getLogger().setLevel(log_level)
    if args.stderr_file:
        stderr_writer = [TextFileWriter(filename=args.stderr_file,
                                        split_by_date=True)]
        logging.getLogger().addHandler(StdErrLoggingHandler(stderr_writer))

    logging.info('Starting CachedDataServer')
    server = CachedDataServer(port=args.port,
                              interval=args.interval,
                              back_seconds=args.back_seconds,
                              max_records=args.max_records,
                              min_back_records=args.min_back_records,
                              cleanup_interval=args.cleanup_interval,
                              disk_cache=args.disk_cache)

    # Only create reader(s) if they've given us a network to read from;
    # otherwise, count on data coming from websocket publish
    # connections.
    if args.udp:
        readers = []
        # Readers may either be just a port (to listen for broadcast) or
        # a multicast_group:port to listen for multicast.
        for udp_spec in args.udp.split(','):
            group_port = udp_spec.split(':')
            port = int(group_port[-1])
            multicast_group = group_port[-2] if len(group_port) == 2 else ''
            readers.append(UDPReader(port=port, source=multicast_group))
        transform = FromJSONTransform()
        reader = ComposedReader(readers=readers, transforms=[transform])

    # Loop, reading data and writing it to the cache
    try:
        while True:
            if args.udp:
                record = reader.read()
                server.cache_record(record)
            else:
                time.sleep(args.interval)

    except KeyboardInterrupt:
        logging.warning('Received KeyboardInterrupt - shutting down')
        if args.disk_cache:
            logging.warning(
                'Will try to save to disk cache prior to shutdown...')
            server.cache.save_to_disk(args.disk_cache)
        server.quit()
