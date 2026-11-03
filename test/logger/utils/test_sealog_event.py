#!/usr/bin/env python3
"""Tests for to_event() in logger/utils/sealog_event.py."""
import unittest

from logger.utils.das_record import DASRecord  # noqa: E402
from logger.utils.sealog_event import to_event  # noqa: E402


class TestToEvent(unittest.TestCase):

    def options(self, event):
        return {option['event_option_name']: option['event_option_value']
                for option in event.event_options}

    def test_option_names_without_field_map(self):
        """Each event_option_<name> field becomes an option called <name> -
        including names starting with letters in 'event_option_' (#676)."""
        record = DASRecord(data_id='logger_manager', timestamp=1792677791,
                           fields={'event_value': 'mode_changed',
                                   'event_option_previous_mode': 'off',
                                   'event_option_note': 'started',
                                   'event_option_reason': 'operator',
                                   'not_an_option': 1})
        event = to_event(record)
        self.assertEqual(event.event_value, 'mode_changed')
        self.assertEqual(self.options(event), {'previous_mode': 'off',
                                               'note': 'started',
                                               'reason': 'operator'})

    def test_field_map(self):
        record = DASRecord(data_id='probe', timestamp=1792677791,
                           fields={'event_option_previous_mode': 'off'})
        configs = {'probe': {'field_map': {'previous_mode': 'From mode'}}}
        self.assertEqual(self.options(to_event(record, configs)), {'From mode': 'off'})


if __name__ == '__main__':
    unittest.main()
