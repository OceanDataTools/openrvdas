#!/usr/bin/env python3

import sys
import json
import pprint
import logging
from typing import Union, Optional

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.timestamp import time_str  # noqa:E402
from logger.utils.das_record import DASRecord  # noqa: E402

class SealogEvent:
    """SealogEvent is a structured representation of a Sealog event object.
    Class includes help methods like __str__, __eq__ and as_json
    """
    ############################

    def __init__(self, json_str=None, event_value=None, event_author=None,
                 timestamp=None, event_free_text=None, event_options=None):
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
            self.event_value = parsed.get('event_value')
            self.event_author = parsed.get('event_author')
            ts = parsed.get('timestamp')
            if isinstance(ts, int):
                self.timestamp = time_str(ts)
            else:
                self.timestamp = ts
            self.timestamp = parsed.get('timestamp')
            self.event_free_text = parsed.get('event_free_text', "")
            self.event_options = parsed.get('event_options', [])
        else:
            # self.source =
            self.event_value = event_value
            self.event_author = event_author
            self.timestamp = time_str(timestamp) if isinstance(timestamp, int) else timestamp
            self.event_free_text = event_free_text or ""
            self.event_options = event_options or []

    ############################
    def as_json(self, pretty=False) -> str:
        """Return DASRecord as a JSON string."""
        json_dict = {
            'event_value': self.event_value,
            'event_author': self.event_author,
            'ts': self.timestamp,
            'event_free_text': self.event_free_text,
            'event_options': self.event_options
        }

        json_dict = {k: v for k, v in json_dict.items() if v is not None}

        if pretty:
            return json.dumps(json_dict, indent=4)
        else:
            return json.dumps(json_dict)

    ############################
    def __str__(self):
        das_dict = {
            'event_value': self.event_value,
            'event_author': self.event_author,
            'ts': self.timestamp,
            'event_free_text': self.event_free_text,
            'event_options': self.event_options
        }

        das_dict = {k: v for k, v in das_dict.items() if v is not None}

        return pprint.pformat(das_dict)

    ############################
    def __eq__(self, other) -> bool:
        return (other and
                self.event_value == other.event_value and
                self.event_author == other.event_author and
                self.timestamp == other.timestamp and
                self.event_free_text == other.event_free_text and
                self.event_options == other.event_options)


############################
def to_event(record: Union[SealogEvent, DASRecord, str], configs: Optional[dict] = None) -> SealogEvent:
    """
    Uses an object of configs to translates a DASRecord object or json string to a SealogEvent
    object.
    """

    if not configs:
        configs = {
            '_default': {
                'event_free_text': "",
                'field_map': None
            }
        }

    if isinstance(record, SealogEvent):
        return record

    if isinstance(record, str):
        event = SealogEvent(json_str=record)
        return event

    record = json.loads(record.as_json())

    data_id = record.get("data_id", "_default")
    config = configs.get(data_id) or configs.get('_default', {})

    event_value = record['fields'].get("event_value") or config.get("event_value", 'FROM_OPENRVDAS')
    event_author = record['fields'].get("event_author") or config.get("event_author")
    event_free_text = record['fields'].get("event_free_text") or config.get("event_free_text", "")

    ts_str = time_str(record["timestamp"]) if record.get("timestamp") else None

    event_options = [
        {"event_option_name": k, "event_option_value": v}
        for k, v in config.get("event_options", {}).items()
    ]

    field_map = config.get("field_map", {})

    record_fields = record.get("fields", {})
    
    if not field_map:
        event_options.extend([
            {"event_option_name": k.lstrip("event_option_"), "event_option_value": v}
            for k, v in record_fields.items()
            if k.startswith("event_option_")
        ])
    else:
        event_options.extend(
            {"event_option_name": dst, "event_option_value": record_fields[f'event_option_{src}']}
            for src, dst in field_map.items()
            if f'event_option_{src}' in record_fields
        )

    event =  SealogEvent(
        event_value=event_value,
        timestamp=ts_str,
        event_author=event_author,
        event_free_text=event_free_text,
        event_options=event_options
    )

    return event

