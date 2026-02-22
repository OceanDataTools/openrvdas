#!/usr/bin/env python3

import json
import pprint
import logging

from logger.utils.timestamp import timestamp as timestamp_method  # noqa: E402


class DASRecord:
    """DASRecord is a structured representation of the field names and
    values (and metadata) contained in a sensor record.
    """
    ############################

    def __init__(self, json_str=None, data_id=None, message_type=None,
                 timestamp=0, fields=None, metadata=None):
        """
        If a json string is passed, it is parsed into a dictionary and its
        values for timestamp, fields and metadata are copied in. Otherwise,
        the DASRecord object is initialized with the passed-in values for
        instrument, timestamp, fields (a dictionary of fieldname-value pairs)
        and metadata.

        If timestamp is not specified, the instance will use the current time.
        """
        if json_str:
            parsed = json.loads(json_str)
            self.data_id = parsed.get('data_id')
            self.message_type = parsed.get('message_type')
            self.timestamp = parsed.get('timestamp')
            self.fields = parsed.get('fields', {})
            self.metadata = parsed.get('metadata', {})
        else:
            # self.source =
            self.data_id = data_id
            self.message_type = message_type
            self.timestamp = timestamp or timestamp_method()
            if fields is None:
                self.fields = {}
            else:
                self.fields = fields
            if metadata is None:
                self.metadata = {}
            else:
                self.metadata = metadata

    ############################
    def as_json(self, pretty=False):
        """Return DASRecord as a JSON string."""
        json_dict = {
            'data_id': self.data_id,
            'message_type': self.message_type,
            'timestamp': self.timestamp,
            'fields': self.fields,
            'metadata': self.metadata
        }
        if pretty:
            return json.dumps(json_dict, sort_keys=True, indent=4)
        else:
            return json.dumps(json_dict)

    ############################
    def __str__(self):
        das_dict = {
            'data_id': self.data_id,
            'message_type': self.message_type,
            'timestamp': self.timestamp,
            'fields': self.fields,
            'metadata': self.metadata
        }
        return pprint.pformat(das_dict)

    ############################
    def __eq__(self, other):
        return (other and
                self.data_id == other.data_id and
                self.message_type == other.message_type and
                self.timestamp == other.timestamp and
                self.fields == other.fields and
                self.metadata == other.metadata)

    ############################
    def __setitem__(self, field, value):
        self.fields[field] = value

    ############################
    def __getitem__(self, field):
        try:
            return self.fields[field]
        except KeyError:
            logging.error(f'No field "{field}" found in DASRecord {self}')
            raise

    ############################
    def __delitem__(self, field):
        try:
            del self.fields[field]
        except KeyError:
            logging.error(f'Attempt to delete non-existent field "{field}" in DASRecord: {self}')

    ############################
    def get(self, field, default=None):
        return self.fields.get(field, default)


def to_das_record_list(record, data_id=None):
    """Utility function to normalize different types of records into a
    list of DASRecords.

    Take input in one of these three formats:
       - DASRecord
       - a single record dict with keys 'timestamp' and 'fields'
       - a field dict of format
         ``` {field_name: [(timestamp, value), (timestamp, value),...],
              field_name: [(timestamp, value), (timestamp, value),...],
             }
         ```
    and convert it into a list of zero or more DASRecords.
    """
    # What type of record is this?
    if not record:
        return []

    # If it's a list, assume it's already a list of DASRecords
    if isinstance(record, list):
        return record

    # If it's a single DASRecord, it's easy
    if isinstance(record, DASRecord):
        return [record]

    # At this point, if it's not a dict, we don't know *what* it is
    if not isinstance(record, dict):
        logging.error('Unknown type of input passed to to_das_record_list: %s: %s',
                      type(record), record)
        return []

    # If it's a single timestamp dict, it's easy
    elif 'timestamp' in record and 'fields' in record:
        return [DASRecord(data_id=data_id,
                          timestamp=record['timestamp'],
                          fields=record['fields'],
                          metadata=record.get('metadata'))]

    # If here, we believe we've received a field dict, in which each
    # field may have multiple [timestamp, value] pairs. First thing we
    # do is reformat the data into a map of
    #        {timestamp: {field:value, field:value},...}}
    try:
        by_timestamp = {}
        for field, ts_value_list in record.items():
            if not isinstance(ts_value_list, list):
                logging.warning('Expected field_name: [(timestamp, value),...] pairs, '
                                'found %s: %s', field, ts_value_list)
                continue
            for (timestamp, value) in ts_value_list:
                if timestamp not in by_timestamp:
                    by_timestamp[timestamp] = {}
                by_timestamp[timestamp][field] = value

        # Now copy the entries into an ordered-by-timestamp list.
        results = [DASRecord(data_id=data_id, timestamp=ts, fields=by_timestamp[ts])
                   for ts in sorted(by_timestamp)]
        return results
    except ValueError:
        logging.error('Badly-structured field dictionary: %s: %s',
                      field, pprint.pformat(ts_value_list))
        return []


def collect_metadata_for_fields(field_names, timestamp, metadata,
                                metadata_interval, metadata_last_sent):
    """
    Collect metadata for fields that are due to be sent based on the interval.

    This function is shared between RecordParser and RegexParser to avoid
    code duplication.

    Args:
        field_names: Iterable of field names to check for metadata.
        timestamp: Current record timestamp (numeric).
        metadata: Dict mapping field names to their metadata dicts.
        metadata_interval: Minimum seconds between metadata sends per field.
        metadata_last_sent: Dict tracking last send time per field (modified in place).

    Returns:
        Dict with 'fields' key containing metadata to inject, or None if no
        metadata is due to be sent.
    """
    if not metadata or not metadata_interval:
        return None

    metadata_fields = {}
    for field_name in field_names:
        last_sent = metadata_last_sent.get(field_name, 0)
        if timestamp - last_sent > metadata_interval:
            field_metadata = metadata.get(field_name)
            if field_metadata:
                metadata_fields[field_name] = field_metadata
                metadata_last_sent[field_name] = timestamp

    return {'fields': metadata_fields} if metadata_fields else None
