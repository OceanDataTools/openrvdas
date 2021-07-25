import logging

from logger.utils.das_record import DASRecord  # noqa: E402

KNOWN_FIELD_TYPES = ['polar']


################################################################################
def polar_diff(last_value, value):
    return ((value - last_value) + 180) % 360 - 180


################################################################################
class DeltaTransform:
    def __init__(self, rate=False, field_type=None):
        """Return a DASRecord (or dict, depending on input record type) with
        each field's delta in value from it's previous value. If a field
        is absent, it will be omitted. The first time a field appears, it
        will be omitted (as there is no previous value to delta from). If
        no deltas are available, None will be returned.

        rate — If True, return the rate of change (delta/second). If a
               list of field names, return rate of change for field names
               in the list, simple delta for all others.  fields, or just
               return the delta.

        field_type — if not None, should be a dict mapping field names to
               special field types, if any. Currently, only 'polar' is
               implemented.
        """
        if type(rate) not in [bool, list]:
            raise ValueError('"rate" argument in DeltaTransform must be either '
                             'a list or Boolean. Found type %s' % type(rate))
        if field_type:
            if not type(field_type) is dict:
                raise ValueError('"field_type" argument in DeltaTransform must be '
                                 ' either None or a dict. Found "%s"' %
                                 type(field_type))
            # Check that any specified field types are ones we know about.
            for field_name, this_field_type in field_type.items():
                if this_field_type not in KNOWN_FIELD_TYPES:
                    raise ValueError('Unknown field_type specified for field %s: %s. '
                                     'Known field types are: %s' %
                                     (field_name, this_field_type, KNOWN_FIELD_TYPES))
        self.rate = rate
        self.field_type = field_type

        # Dict of {field_name: (previous_timestamp, previous_value)} pairs
        self.last_value_dict = {}

    ############################
    def transform(self, record):
        if not record:
            return None

        fields = {}

        if type(record) is DASRecord:
            fields = record.fields
            timestamp = record.timestamp

        elif type(record) is dict:
            fields = record.get('fields', None)
            timestamp = record.get('timestamp', None)

        elif type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record))
            return results

        else:
            logging.info('Record passed to DeltaTransform was neither a dict nor a '
                         'DASRecord. Type was %s: %s' % (type(record), str(record)[:80]))
            return None

        if fields is None:
            logging.info('Record passed to DeltaTransform does not have "fields": %s', record)
            return None

        if timestamp is None:
            logging.info('Record passed to DeltaTransform does not have "timestamp": %s', record)
            return None

        delta_values = {}

        for key, value in fields.items():
            # If we don't have a previous value for this field, store the
            # current one and move on to the next field.
            if key not in self.last_value_dict:
                self.last_value_dict[key] = (timestamp, value)
                continue

            last_timestamp, last_value = self.last_value_dict.get(key, (None, None))

            # Does this field have a special type?
            if type(self.field_type) is dict:
                this_field_type = self.field_type.get(key, None)
            else:
                this_field_type = self.field_type

            # What do we do with this field_type? 'None' is a simple diff
            if this_field_type == 'polar':
                delta_values[key] = polar_diff(last_value, value)
            elif this_field_type is None:
                delta_values[key] = value - last_value
            else:
                raise ValueError('DeltaTransform configured with unrecognized '
                                 'field type for %s: "%s"', key, this_field_type)

            # Are we doing rate or simple diff for this field?
            if self.rate is True or type(self.rate) is list and key in self.rate:
                time_diff = timestamp - last_timestamp
                # If rate, make sure it's a valid time difference. Bail if it isn't.
                if time_diff <= 0:
                    logging.warning('Invalid difference in successive timestamps for '
                                    'field %s:  %g -> %g', key, last_timestamp, timestamp)
                    return None
                delta_values[key] = delta_values[key] / time_diff

            # Finally, save the current values for next time
            self.last_value_dict[key] = (timestamp, value)

        # If, at the end of it all, we don't have any fields, return None
        if not delta_values:
            return None

        # If they gave us a dict, return a dict; if they gave us a
        # DASRecord, return a DASRecord.
        if type(record) is dict:
            return {'timestamp': timestamp, 'fields': delta_values}

        return DASRecord(timestamp=timestamp, fields=delta_values)
