#!/usr/bin/env python3
"""
TODO: option to initialize with a message to be output in case of failure.

TODO: option to intialize with a flag saying whether records will be
DASRecords or dictionary, or...?

"""

import logging
import sys

from os.path import dirname, realpath
from typing import Union
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
#
class QCFilterTransform(Transform):
    """
    Transform that returns None unless values in passed DASRecord are out of
    bounds, in which case return a warning message. Also return warning if
    something other than a DASRecord or dict (or list of DASRecord or dict)
    is passed.

    Note that this module is due to be replaced by a more general value
    matching transform, as per GitHub feature request:

    https://github.com/OceanDataTools/openrvdas/issues/406
    """
    def __init__(self, bounds, message=None, **kwargs):
        """
        ```
        bounds   A comma-separated list of conditions of the format

                    <field_name>:<lower_bound>:<upper_bound>

                 Either <lower_bound> or <upper_bound> may be empty.

        message  Optional string to be output instead of default when bounds
                 are violated
        ```
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        self.message = message
        self.bounds = {}
        for condition in bounds.split(','):
            try:
                (var, lower_str, upper_str) = condition.split(':')
                lower = None if lower_str == '' else float(lower_str)
                upper = None if upper_str == '' else float(upper_str)
                self.bounds[var] = (lower, upper)
            except ValueError:
                raise ValueError('QCFilterTransform bounds must be colon-separated '
                                 'triples of field_name:lower_bound:upper_bound. '
                                 'Found "%s" instead.' % condition)

    ############################
    def transform(self, record: Union[DASRecord, dict]) -> str:
        """Does record violate any bounds?"""

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            return self.digest_record(record)  # inherited from BaseModule()

        # If here, we must be either a DASRecord or dict
        if type(record) is DASRecord:
            fields = record.fields
        elif type(record) is dict:
            if 'fields' in record:
                fields = record['fields']
            else:
                fields = record
        else:
            logging.warning(f'QCFilterTransform code error. Non-conforming record '
                            f'of type {type(record)} got through checks: {record}')

        errors = []
        for bound in self.bounds:
            if bound not in fields:
                continue

            value = fields[bound]  # Already checked for existence
            lower, upper = self.bounds[bound]  # Unpack bounds

            if not isinstance(value, (int, float)):
                err = f'{bound}: non-numeric value: "{value}"'
                logging.warning(err)
                errors.append(err)
            elif lower is not None and value < lower:
                err = f'{bound}: {value} < lower bound {lower}'
                logging.warning(err)
                errors.append(err)
            elif upper is not None and value > upper:
                err = f'{bound}: {value} > upper bound {upper}'
                logging.warning(err)
                errors.append(err)

        # If no errors, return None. Otherwise either return the specified
        # message (if we've been given one), or the joined string of
        # specific failures.
        if not errors:
            return None

        if self.message:
            return self.message
        else:
            return '; '.join(errors)
