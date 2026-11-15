#!/usr/bin/env python3
"""contrib/csiro's RegexRecordParser converts field values without
evaluating them.

It used to convert a value by eval()-ing '<data_type>("<value>")', and the
value comes from the incoming record. A value containing a double quote
could close the string literal and run arbitrary Python. The bundled
example definitions capture ZDA's LocalZoneHours with '.*' and type it
'int', so a crafted ZDA sentence was enough.
"""
import contextlib
import io
import logging
import unittest

from contrib.csiro.logger.utils.regex_record_parser import RegexRecordParser  # noqa: E402

DEFINITIONS = 'contrib/csiro/test/Regex_device_catalogue.yaml'
ZDA = 'seap 2022-08-17T01:39:42.459365Z $GPZDA,143357.30,30,01,2023,{hours},0*63'
MARKER = 'injected code ran'


class TestCSIRORegexRecordParserConversion(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.parser = RegexRecordParser(definition_path=DEFINITIONS)

    def parse(self, record):
        """Parse record, returning (fields, anything it printed)."""
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = self.parser.parse_record(record)
        return result['fields'], output.getvalue()

    def test_values_are_converted(self):
        fields, _ = self.parse(ZDA.format(hours='-5'))
        self.assertEqual(fields['LocalZoneHours'], -5)
        self.assertEqual(fields['GPSTime'], 143357.3)
        self.assertEqual(fields['GPSYear'], 2023)

    def test_crafted_value_is_not_executed(self):
        # Without commas, so that the whole payload lands in LocalZoneHours
        payload = f'0")+__import__("builtins").print("{MARKER}")+int("0'
        fields, printed = self.parse(ZDA.format(hours=payload))
        self.assertNotIn(MARKER, printed)
        # Not convertible to int, so it stays the string it arrived as
        self.assertEqual(fields['LocalZoneHours'], payload)

    def test_unknown_data_type_is_left_as_a_string(self):
        self.parser.data_type_map['Seapath330']['LocalZoneHours'] = 'complex'
        fields, _ = self.parse(ZDA.format(hours='3'))
        self.assertEqual(fields['LocalZoneHours'], '3')


if __name__ == '__main__':
    unittest.main()
