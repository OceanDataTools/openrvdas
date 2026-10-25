#!/usr/bin/env python3
"""Parse every NBP1406 sample data file with the NBP1406 device definitions,
and check that the result is what it was when the expected summary was
written (#688).

The NBP1406 cruise is the example people copy, and its device definitions
draw on logger/devices/NMEA_0183.yaml and contrib/devices/. A change to any
of those files that alters what the example's data parses to - a renamed
field, a sentence that no longer matches - fails this test, rather than
passing unnoticed.

If a change is intended, regenerate the summary and commit it with the
change:

    python test/logger/utils/test_nbp1406_device_definitions.py --update
"""
import glob
import hashlib
import json
import logging
import os
import sys
import time
import unittest

from logger.utils.record_parser import RecordParser  # noqa: E402

DEFINITIONS = 'test/NBP1406/devices/nbp_devices.yaml'
DATA_FILES = 'test/NBP1406/data/*/raw/*'
EXPECTED = 'test/NBP1406/devices/expected_parse_summary.json'


def parse_summary():
    """{device: {records, parsed, fields, sha256}} for the sample files.

    Parsed in UTC: the 'ti' format reads a timestamp with no time zone, as
    the NBP winches send, as local time, so the result would otherwise depend
    on the machine's time zone - and on whether an earlier test changed it."""
    logging.disable(logging.WARNING)
    saved_tz = os.environ.get('TZ')
    os.environ['TZ'] = 'UTC'
    time.tzset()
    try:
        parser = RecordParser(definition_path=DEFINITIONS)
        summary = {}
        for path in sorted(glob.glob(DATA_FILES)):
            device = path.split(os.sep)[3]
            digest = hashlib.sha256()
            fields, parsed, records = set(), 0, 0
            with open(path) as f:
                for line in f:
                    records += 1
                    record = parser.parse_record(f'{device} {line.rstrip()}')
                    parsed_fields = (record or {}).get('fields') or {}
                    if parsed_fields:
                        parsed += 1
                    fields.update(parsed_fields)
                    digest.update(json.dumps(parsed_fields, sort_keys=True).encode())
                    digest.update(b'\n')
            summary[device] = {'records': records, 'parsed': parsed,
                               'fields': sorted(fields), 'sha256': digest.hexdigest()}
        return summary
    finally:
        if saved_tz is None:
            del os.environ['TZ']
        else:
            os.environ['TZ'] = saved_tz
        time.tzset()
        logging.disable(logging.NOTSET)


class TestNBP1406DeviceDefinitions(unittest.TestCase):

    def test_sample_data_parses_as_expected(self):
        with open(EXPECTED) as f:
            expected = json.load(f)
        actual = parse_summary()
        self.assertEqual(sorted(actual), sorted(expected), 'devices with sample data')
        for device in sorted(expected):
            with self.subTest(device=device):
                # Field names first: they give the most useful message
                self.assertEqual(actual[device]['fields'], expected[device]['fields'])
                self.assertEqual(actual[device]['parsed'], expected[device]['parsed'])
                self.assertEqual(actual[device]['sha256'], expected[device]['sha256'],
                                 'same fields, but some parsed values differ')


if __name__ == '__main__':
    if '--update' in sys.argv:
        with open(EXPECTED, 'w') as f:
            json.dump(parse_summary(), f, indent=2, sort_keys=True)
            f.write('\n')
        print(f'Wrote {EXPECTED}')
    else:
        unittest.main()
