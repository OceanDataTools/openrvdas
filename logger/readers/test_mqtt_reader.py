#!/usr/bin/env python3

import logging
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.mqtt_writer import MQTTWriter  # noqa: E402
from logger.readers.mqtt_reader import MQTTReader  # noqa: E402

# Don't barf if they don't have redis installed. Only complain if
# they actually try to use it, below
try:
    # import the client | $ pip installing paho-mqtt is necessary
    import paho.mqtt.client as mqtt  # noqa: F401
    PAHO_ENABLED = True
except ModuleNotFoundError:
    PAHO_ENABLED = False

SAMPLE_DATA = [
    's330 2017-11-04T06:54:07.173130Z $INZDA,002033.17,07,08,2014,,*7A',
    's330 2017-11-04T06:54:09.210395Z $INZDA,002034.17,07,08,2014,,*7D',
    's330 2017-11-04T06:54:11.248784Z $INZDA,002035.17,07,08,2014,,*7C',
    's330 2017-11-04T06:54:13.290817Z $INZDA,002036.17,07,08,2014,,*7F',
    's330 2017-11-04T06:54:15.328116Z $INZDA,002037.17,07,08,2014,,*7E',
    's330 2017-11-04T06:54:17.371220Z $INZDA,002038.17,07,08,2014,,*71',
    's330 2017-11-04T06:54:19.408518Z $INZDA,002039.17,07,08,2014,,*70',
]

broker_address = '1883'
channel = 'pathOfDevices'
client_name = 'Instance1'


##############################################################################
class TestMQTTReader(unittest.TestCase):

    @unittest.skipUnless(PAHO_ENABLED, 'Paho MQTT not installed; tests of MQTT '
                         'functionality will not be run.')
    def test_read(self):

        try:
            # Creating a new instance from the mqtt broker address above
            # try to connect
            writer = MQTTWriter(broker_address, channel, client_name)
            reader = MQTTReader(broker_address, channel, client_name)

            for i in range(len(SAMPLE_DATA)):
                writer.write(SAMPLE_DATA[i])
                self.assertEqual(SAMPLE_DATA[i], reader.read())
        except:  # noqa: E722
            self.skipTest("No MQTT broker found - skipped test_mqtt_reader")


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
