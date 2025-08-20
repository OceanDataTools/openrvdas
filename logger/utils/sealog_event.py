import sys
import logging
from typing import Union

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.timestamp import time_str  # noqa:E402
from logger.utils.das_record import DASRecord  # noqa: E402

class SealogEvent:
    """DASRecord is a structured representation of the field names and
    values (and metadata) contained in a sensor record.
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


def to_event(self, record: Union[DASRecord, str], configs: list) -> SealogEvent:

    if isinstance(record, str):
        event = SealogEvent(json_str=record)
        return event

    data_id = record.get("data_id", "_default")
    config = configs.get(data_id, {})

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

    event =  SealogEvent(
        event_value=event_value,
        timestamp=ts_str,
        event_author=config.get("event_author"),
        event_free_text=config.get("event_free_text", ""),
        event_options=event_options
    )

    return event