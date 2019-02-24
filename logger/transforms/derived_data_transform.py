#!/usr/bin/env python3
"""Contains DerivedDataTransform and ComposedDerivedDataTransform.

A DerivedDataTransform is intended to be fed with a dictionary of
field values and returns a dictionary of field values. It is required
to implement a fields() method reporting which fields it's interested
in, to allow the caller (typically a ComposedDerivedDataTransform) to
call it only when new values are available for fields in which it is
interested.

A ComposedDerivedDataTransform is initialized with a list of
DerivedDataTransforms. The transform() method then takes either
DASRecords or {field:[[timestamp, value],...]} dictionaries, caches
the received values, distributes them among the contained
DerivedDataTransforms, and aggregates their outputs, either into an
anonymous DASRecord or a field dictionary, depending on how it was
initialized.

The transforms can take data in one of three formats (and will return
data in the same format as the input:
 - DASRecord
 - a single record dict with keys 'timestamp' and 'fields'
 - a field dict of format {data_id: [(timestamp, value), 
                                     (timestamp, value),
                                     ...)]}
"""
import logging
import pprint
import sys
from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from collections import OrderedDict

from logger.transforms.transform import Transform
from logger.utils import formats
from logger.utils.das_record import DASRecord

################################################################################
class DerivedDataTransform(Transform):
  """
  Base class for derived data transforms that take in a dict of values (only
  some of which they are interested in) and emit a dict of derived values.

  Required methods are:

  fields() - return a list of field_names in which we are interested. We
    will only be called when there are new values available for one or
    more of these fields.

  transform(value_dict, timestamp_dict=None) - look for the fields we're
    interested in (and optionally, their timestamps, if available) and
    generate a DASRecord containing the derived values. If timestamp_dict
    is available, the timestamp on the DASRecord would typically be the
    latest timestamp of any field value used, otherwise the current time.
  """
  ############################
  def __init__(self):
    """Abstract base class for DerivedDataTransforms."""
    super().__init__(input_format=formats.Python, output_format=formats.Python)

  ############################
  def fields(self):
    """What fields is this transform interested in?"""
    raise NotImplementedError('"fields()" method not defined for abstract '
                              'class DerivedDataTransform')

  ############################
  def transform(self, value_dict, timestamp_dict=None):
    """Compute our new derived values from the value dict."""
    raise NotImplementedError('"transform()" method not defined for abstract '
                              'class DerivedDataTransform')


################################################################################
class ComposedDerivedDataTransform(Transform):
  """Container for DerivedDataTransforms. Initialize with a list of
  DerivedDataTransforms. The transform() method then takes either
  DASRecords or {field:[[timestamp, value],...]} dictionaries, caches
  the received values, distributes them among the contained
  DerivedDataTransforms, and aggregates their outputs (either into an
  anonymous DASRecord or a field dictionary, depending on how it was
  initialized).
  """
  ############################
  def __init__(self, transforms):
    """Composed transform that contains DerivedDataTransforms."""
    super().__init__(input_format=formats.Python, output_format=formats.Python)

    # All transforms we're passed must be DerivedDataTransforms
    for transform in transforms:
      if not DerivedDataTransform in type(transform).mro():
        raise TypeError('Transforms passed to ComposedDerivedDataTransform '
                        'must be of type DerivedDataTransform. Received %s',
                        type(transform))

    # Register which fields each transform is interested in so that we
    # only call it when we have an update for one or more of those fields.
    self.fields = {}
    for transform in transforms:
      for field in transform.fields():
        if not field in self.fields:
          self.fields[field] = set()
        self.fields[field].add(transform)

    self.transforms = transforms

    self.values = {}
    self.timestamps = {}

  ############################
  def transform(self, record):
    """Take input in one of three formats, transform it appropriately, and
    return data in that same format as received:
       - DASRecord
       - a single record dict with keys 'timestamp' and 'fields'
       - a field dict of format {data_id: [(timestamp, value), 
                                           (timestamp, value),
                                           ...]}
    """
    if not record:
      return

    # What type of record is this?
    if type(record) is DASRecord:
      record_type = 'DASRecord'
      timestamp = record.timestamp
      fields = record.fields
    elif type(record) is dict and 'timestamp' in record and 'fields' in record:
      record_type = 'SingleDict'
      timestamp = record.get('timestamp', None)
      fields = record.get('fields', {})
    elif type(record) is dict:
      record_type = 'FieldDict'
      fields = record
    else:
      raise TypeError('ComposedDerivedDataTransform.transform(record) '
                      'received record of inappropriate type: %s\n%s',
                      type(record), pprint.pformat(record))

    # DASRecords and SingleDicts are easy - we only have one timestamp
    # to deal with, so only have to run each transform once.
    if record_type in ('DASRecord', 'SingleDict'):
      # Which transforms are interested in values contained in record?
      transforms_to_run = set()
      for field, value in fields.items():
        field_transforms = self.fields.get(field, set())
        transforms_to_run.update(field_transforms)

        self.values[field] = value
        self.timestamps[field] = timestamp

      # Run all transforms that have registered interest in these
      # fields, then aggregate results into a single dict.
      results = {}
      for transform in transforms_to_run:
        t_results = transform.transform(self.values, self.timestamps)
        if t_results:
          results.update(t_results)

      # Return an anonymous DASRecord or single dict with the results
      # we've aggregated.
      if not results:
        return None

      if record_type == 'DASRecord':
        return DASRecord(timestamp=timestamp, fields=results)
      else:
        return {'timestamp': timestamp, 'fields': results}

    # If here, we believe we've received a field dict, in which each
    # field may have multiple [timestamp, value] pairs. First thing we
    # do is reformat the data into a map of
    #        {timestamp: {field:value, field:value],...}}
    values_by_timestamp = {}
    try:
      for field, ts_value_list in fields.items():
        for (timestamp, value) in ts_value_list:
          if not timestamp in values_by_timestamp:
            values_by_timestamp[timestamp] = {}
          values_by_timestamp[timestamp][field] = value
    except ValueError:
      logging.error('Badly-structured field dictionary: %s: %s',
                    field, pprint.pformat(ts_value_list))

    # Now go through each timestamp, update the values in it, then run
    # the transforms that are interested in the values that have
    # updated. Append the resulting transformed [timestamp, value]
    # pairs to the appropriate field name.
    results = {}
    for timestamp in sorted(values_by_timestamp):
      fields = values_by_timestamp[timestamp]
      logging.debug('timestamp %f, fields: %s', timestamp, fields)

      # Which transforms are interested in values contained in this
      # particular timestamp?
      transforms_to_run = set()
      for field, value in fields.items():
        field_transforms = self.fields.get(field, set())
        transforms_to_run.update(field_transforms)

        self.values[field] = value
        self.timestamps[field] = timestamp

      # Run all transforms and aggregate results into a single dict
      for transform in transforms_to_run:
        field_values = transform.transform(self.values, self.timestamps)
        if not field_values:
          continue

        for field, value in field_values.items():
          if not field in results:
            results[field] = []
          results[field].append([timestamp, value])

    return results or None
