#!/usr/bin/env python3
"""
TODO: option to initialize with a message to be output in case of failure.

TODO: option to intialize with a flag saying whether records will be
DASRecords or dictionary, or...?

"""

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
#
class ValueFilterTransform(Transform):
    """
    Transform that filters out values in a passed DASRecord that are out of bounds."""

    def __init__(self, bounds):
        """
        ```
        bounds   A comma-separated list of conditions of the format

                    <field_name>:<lower_bound>:<upper_bound>

                 Either <lower_bound> or <upper_bound> may be empty.
        ```
        """
        self.bounds = {}
        for condition in bounds.split(','):
            try:
                (var, lower_str, upper_str) = condition.split(':')
                lower = None if lower_str == '' else float(lower_str)
                upper = None if upper_str == '' else float(upper_str)
                self.bounds[var] = (lower, upper)
            except ValueError:
                raise ValueError('ValueFilterTransform bounds must be colon-separated '
                                 'triples of field_name:lower_bound:upper_bound. '
                                 f'Found "{condition}" instead.')

    ############################
    def transform(self, record):
        """Does record violate any bounds?"""
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
            fields = record.fields
        elif type(record) is dict:
            if 'fields' in record:
                fields = record['fields']
            else:
                fields = record
        else:
            return (f'Record passed to ValueFilterTransform was neither a dict nor a '
                    f'DASRecord. Type was {type(record)}: {str(record)[:80]}')

        errors = []
        for bound in self.bounds:
            if bound not in fields:
                continue
            (lower, upper) = self.bounds[bound]  # what are the upper/lower bounds?

            value = fields.get(bound)  # what is the record's value of this field?

            # We expect field value to be numeric; if not, complain lightly and remove it
            if type(value) is not int and type(value) is not float:
                logging.info(f'ValueFilterTransform found non-numeric value for {bound}: {value}')
                del fields[bound]

            # If value exists and is out of bounds, delete it
            elif lower is not None and value < lower:
                logging.info(f'Value for {bound}: {value} less than lower bound {lower}')
                del fields[bound]
            elif upper is not None and value > upper:
                logging.info(f'Value for {bound}: {value} greater than upper bound {upper}')
                del fields[bound]

        return record

