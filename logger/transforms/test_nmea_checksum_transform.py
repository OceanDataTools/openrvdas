# !/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.transforms.nmea_checksum_transform import NMEAChecksumTransform  # noqa: E402


class DummyWriter:
    """Dummy 'Writer' class we can use to test that the write option on
    NMEAChecksumTransform is properly called.
    """

    def __init__(self):
        self.write_message = None

    def write(self, message):
        logging.debug('write called: %s', message)
        self.write_message = message


class TestNMEAChecksumTransform(unittest.TestCase):

    def test_default(self):
        t = NMEAChecksumTransform()

        alpha = '$PSXN,20,1,0,0,0*3A'
        self.assertEqual(t.transform(alpha), alpha)

        beta = '$PSXN,20,1,0,0,0*3C'
        with self.assertLogs(level=logging.WARNING):
            self.assertEqual(t.transform(beta), None)

        # Test that it complains when we get a non-string input
        with self.assertLogs(level=logging.WARNING):
            self.assertEqual(t.transform({1: 3}), None)

    def test_writer(self):
        writer = DummyWriter()
        t = NMEAChecksumTransform(error_message='message: ', writer=writer)

        alpha = '$PSXN,20,1,0,0,0*3A'
        self.assertEqual(t.transform(alpha), alpha)

        beta = '$PSXN,20,1,0,0,0*3C'
        self.assertEqual(t.transform(beta), None)

        # Now test that the error message got sent to the writer
        self.assertEqual(writer.write_message, 'message: $PSXN,20,1,0,0,0*3C')


if __name__ == '__main__':
    unittest.main()
