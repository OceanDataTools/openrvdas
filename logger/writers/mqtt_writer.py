#!/usr/bin/env python3

import logging
import sys

# Don't barf if they don't have paho mqtt installed. Only complain if
# they actually try to use it, below. If it *is* installed, check which
# version, so we know how to call it.
try:
    import paho.mqtt.client as mqtt  # import the client | $ pip installing paho-mqtt is necessary
    PAHO_ENABLED = True

    # Check which paho version is being used
    from pkg_resources import get_distribution, packaging  # noqa: E402
    PAHO_VERSION = get_distribution("paho-mqtt").version
    if packaging.version.parse(PAHO_VERSION) >= packaging.version.parse('2.0.0'):
        USE_VERSION_FLAG = True
    else:
        USE_VERSION_FLAG = False
except ModuleNotFoundError:
    PAHO_ENABLED = False

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.writer import Writer  # noqa: E402


class MQTTWriter(Writer):
    """Write to paho-mqtt broker channel."""

    def __init__(self, broker, channel, client_name=None, qos=0):
        """
        Write text records to a paho-mqtt broker channel.
        ```
        broker       MQTT broker to connect, broker format[###.###.#.###]
        channel      MQTT channel to read from, channel format[@broker/path_of_subscripton]
        client_name  Deprecated
        qos          Quality of service: 0 = at most once, 1 = at least once, 2 = exactly once

        ```
        See /readers/mqtt_reader.py for info on how to start a broker
        """
        if not PAHO_ENABLED:
            raise ModuleNotFoundError('MQTTReader(): paho-mqtt is not installed. Please '
                                      'try "pip install paho-mqtt" prior to use.')
        if qos not in [0, 1, 2]:
            raise ValueError('MQTTWriter parameter qos must be integer value 0, 1 or 2. '
                             f'Found type "{type(qos).__name__}", value "{qos}".')
        self.broker = broker
        self.channel = channel
        self.client_name = client_name
        self.qos = qos

        try:
            if USE_VERSION_FLAG:
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            else:
                self.client = mqtt.Client()

            self.client.connect(broker)
            self.client.subscribe(channel)

            self.client.loop_start()

        except mqtt.WebsocketConnectionError as e:
            logging.error('Unable to connect to broker at %s:%s',
                          self.broker, self.channel)
            raise e

    ############################
    def __del__(self):
        """Clean up the connection once finished"""
        self.client.loop_stop()
        self.client.disconnect()

    ############################
    def write(self, record: str):

        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            self.digest_record(record)  # inherited from BaseModule()
            return

        # If record is not a string, try converting to JSON. If we don't know
        # how, throw a hail Mary and force it into str format
        # if not type(record) is str:
        #  if type(record) in [int, float, bool, list, dict]:
        #    record = json.dumps(record)
        #  else:
        #    record = str(record)

        try:
            self.client.publish(self.channel, record, self.qos)
        except mqtt.WebsocketConnectionError as e:
            logging.error('Unable to connect to broker at %s:%d',
                          self.broker, self.channel)
            raise e
