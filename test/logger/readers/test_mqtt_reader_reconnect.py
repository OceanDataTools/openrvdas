#!/usr/bin/env python3
"""
Unit tests for MQTTReader's handling of a dropped broker connection
(OceanDataTools/openrvdas#578).

These don't need a broker: the paho client is replaced with a fake whose
loop() return codes we control, which is what MQTTReader keys off of.

Run with: python -m pytest test/logger/readers/test_mqtt_reader_reconnect.py
"""

import logging
import unittest
from unittest.mock import patch

from logger.readers.mqtt_reader import MQTTReader  # noqa: E402

try:
    import paho.mqtt.client as mqtt  # noqa: F401
    PAHO_ENABLED = True
except ModuleNotFoundError:
    PAHO_ENABLED = False


##############################
class FakeMessage:
    def __init__(self, payload):
        self.payload = payload


##############################
class FakeClient:
    """Stands in for mqtt.Client. loop() hands back queued return codes."""

    def __init__(self, *args, **kwargs):
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.subscriptions = []
        self.connect_calls = 0
        self.reconnect_calls = 0
        self.disconnect_calls = 0
        # Return codes loop() will yield, in order; then 0 forever.
        self.loop_results = []
        # Exceptions reconnect() should raise before succeeding.
        self.reconnect_failures = 0

    def connect(self, broker, port, **kwargs):
        self.connect_calls += 1

    def subscribe(self, channel, qos=0, **kwargs):
        self.subscriptions.append((channel, qos))

    def disconnect(self):
        self.disconnect_calls += 1

    def reconnect(self):
        self.reconnect_calls += 1
        if self.reconnect_failures > 0:
            self.reconnect_failures -= 1
            raise ConnectionRefusedError('broker still down')

    def loop(self, *args, **kwargs):
        if self.loop_results:
            return self.loop_results.pop(0)
        return 0  # MQTT_ERR_SUCCESS

    # Test helpers -----------------------------------------------------
    def fire_connect(self):
        self.on_connect(self, None, {}, 0, None)

    def fire_disconnect(self, reason='broker went away'):
        # paho 2.x signature: (client, userdata, flags, reason_code, properties)
        self.on_disconnect(self, None, {}, reason, None)

    def deliver(self, payload):
        self.on_message(self, None, FakeMessage(payload))


##############################################################################
@unittest.skipUnless(PAHO_ENABLED, 'paho-mqtt not installed')
class TestMQTTReaderReconnect(unittest.TestCase):

    def _reader(self, **kwargs):
        """Build an MQTTReader backed by a FakeClient."""
        self.fake = FakeClient()
        with patch('logger.readers.mqtt_reader.mqtt.Client',
                   return_value=self.fake):
            reader = MQTTReader('localhost', 'test/channel',
                                client_name='unittest', **kwargs)
        return reader

    ############################
    def test_subscribes_on_every_connect(self):
        """Subscription must be re-established on reconnect, not just at startup."""
        reader = self._reader()
        # Nothing is subscribed until the broker acknowledges the connection...
        self.assertEqual(self.fake.subscriptions, [])
        self.fake.fire_connect()
        self.assertEqual(self.fake.subscriptions, [('test/channel', 0)])
        self.assertTrue(reader.connected)

        # ...and again after a drop and reconnect.
        self.fake.fire_disconnect()
        self.assertFalse(reader.connected)
        self.fake.fire_connect()
        self.assertEqual(self.fake.subscriptions,
                         [('test/channel', 0), ('test/channel', 0)])

    ############################
    def test_disconnect_is_logged(self):
        """The bare minimum asked for in #578: don't drop the connection silently."""
        reader = self._reader()
        with self.assertLogs(level=logging.WARNING) as cm:
            self.fake.fire_disconnect('connection reset')
        self.assertTrue(any('lost connection to broker' in line for line in cm.output),
                        f'no disconnect warning logged; got {cm.output}')
        self.assertTrue(any('connection reset' in line for line in cm.output))
        self.assertFalse(reader.connected)

    ############################
    def test_disconnect_logged_with_paho_1_signature(self):
        """paho 1.x calls on_disconnect(client, userdata, rc) - three args, not five."""
        with patch('logger.readers.mqtt_reader.USE_VERSION_FLAG', False):
            reader = self._reader()
            with self.assertLogs(level=logging.WARNING) as cm:
                # paho 1.x hands us the result code directly
                self.fake.on_disconnect(self.fake, None, 7)
        self.assertTrue(any('lost connection to broker' in line for line in cm.output),
                        f'no disconnect warning logged; got {cm.output}')
        self.assertTrue(any(line.endswith('7') for line in cm.output),
                        f'result code not reported; got {cm.output}')
        self.assertFalse(reader.connected)

    ############################
    def test_read_reconnects_when_loop_fails(self):
        """A failed loop() must trigger a reconnect rather than spinning."""
        reader = self._reader()
        # First loop() reports connection lost; afterwards it's healthy again.
        self.fake.loop_results = [mqtt.MQTT_ERR_CONN_LOST]

        def fake_reconnect():
            self.fake.reconnect_calls += 1
            self.fake.deliver(b'after reconnect')

        self.fake.reconnect = fake_reconnect
        with self.assertLogs(level=logging.WARNING):
            record = reader.read()
        self.assertEqual(self.fake.reconnect_calls, 1)
        self.assertEqual(record, 'after reconnect')

    ############################
    def test_reconnect_backs_off_and_retries(self):
        """Reconnection retries with a growing delay until the broker returns."""
        reader = self._reader(reconnect_delay=0.01, max_reconnect_delay=0.04)
        self.fake.loop_results = [mqtt.MQTT_ERR_CONN_LOST]
        self.fake.reconnect_failures = 3   # fail three times, then succeed

        slept = []
        with patch('logger.readers.mqtt_reader.time.sleep', slept.append):
            with self.assertLogs(level=logging.WARNING):
                self.fake.loop_results = [mqtt.MQTT_ERR_CONN_LOST]
                reader._reconnect(mqtt.MQTT_ERR_CONN_LOST)

        self.assertEqual(self.fake.reconnect_calls, 4)   # 3 failures + success
        # Delay doubles, capped at max_reconnect_delay
        self.assertEqual(slept, [0.01, 0.02, 0.04])

    ############################
    def test_reconnect_disabled_returns_eof(self):
        """With reconnect=False a dropped connection ends the read, visibly."""
        reader = self._reader(reconnect=False)
        self.fake.loop_results = [mqtt.MQTT_ERR_CONN_LOST]
        with self.assertLogs(level=logging.WARNING) as cm:
            record = reader.read()
        self.assertIsNone(record)
        self.assertTrue(any('reconnect is disabled' in line for line in cm.output),
                        f'expected an explanatory warning; got {cm.output}')

    ############################
    def test_healthy_read_is_unaffected(self):
        """The normal path still returns records, as bytes or str."""
        reader = self._reader()
        self.fake.deliver(b'hello world')
        self.assertEqual(reader.read(), 'hello world')

        reader_bytes = self._reader(return_as_bytes=True)
        self.fake.deliver(b'raw bytes')
        self.assertEqual(reader_bytes.read(), b'raw bytes')
        self.assertEqual(self.fake.reconnect_calls, 0)


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
