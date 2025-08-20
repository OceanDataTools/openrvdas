#!/usr/bin/env python3

import logging
import pprint
from typing import Union
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.read_config import read_config  # noqa:E402
from logger.utils.timestamp import time_str  # noqa:E402
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
#
class ToSealogTransform(Transform):
    """
    The class uses a YAML-formatted configuration to determine how to map input
    data fields to Sealog event fields, and converts records accordingly. It
    supports single records or lists of records. It also handles unknown fields
    gracefully using a fallback mechanism.

    Key behaviors:
        - If a record's `data_id` is not found in the configuration, a fallback `_default` config is used.
        - If `field_map` is not specified for a data_id, all fields from the record are included as event options.
        - Any `None` values in the resulting event dictionary are automatically removed.
        - Can process a single record or recursively handle lists of records.

    config_file  - Path to a YAML configuration file specifying:
                   `data_id` to determine which set of rules to apply
                   `event_value` (optional): default event value for the record.
                   `event_author` (optional): author string to include in the event.
                   `event_free_text` (optional): free text string for the event.
                   `field_map` (optional): mapping of input record field names to event option names.
                   `_default` (optional): fallback configuration applied if the record's `data_id` is not found.

    Sample configuration file:
    ---
    qinsy:
        event_value: LOGGING_STATUS
        event_author: "qinsy"
        event_free_text: ""
        field_map:
            status: status
            filename: filename

    _default:
        event_value: UNKNOWN
        event_free_text: ""
        field_map: null

    """

    ############################
    def __init__(self, config_file: str):
        try:
            self.configs = read_config(config_file)
            logging.info('Loaded sealog config file: %s', pprint.pformat(self.configs))
        except Exception as err:
            logging.error("Could not find or could not process config file.  All records will be ignored.")
            pass


    def record_to_event(self, record: DASRecord):

        data_id = record.get("data_id", "_default")
        config = self.configs.get(data_id, {})

        event_value = config.get("event_value", 'FROM_OPENRVDAS')

        ts_str = time_str(record["timestamp"]) if record.get("timestamp") else None

        field_map = config.get("field_map")
        if field_map is None:
            event_options = [
                {"event_option_name": k, "event_option_value": v}
                for k, v in record["fields"].items()
            ]
        else:
            event_options = [
                {"event_option_name": dst_name, "event_option_value": record["fields"][src_field]}
                for src_field, dst_name in field_map.items()
                if src_field in record["fields"]
            ]

        event =  {
            "event_value": event_value,
            "ts": ts_str,
            "event_author": config.get("event_author"),
            "event_free_text": config.get("event_free_text", ""),
            "event_options": event_options
        }

        # remove key/value pairs where value == None
        return {k: v for k, v in event.items() if v is not None}


    def transform(self, record: Union[DASRecord, list]):
        """Parse DASRecord and return Sealog event dict."""
        if record is None:
            return None

        if not self.configs:
            return None

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list.
        if type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record))
            return results

        return self.record_to_event(record)
