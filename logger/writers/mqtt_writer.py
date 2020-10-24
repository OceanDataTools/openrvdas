#!/usr/bin/env python3

import logging
import sys

# Don't barf if they don't have paho mqtt installed. Only complain if
# they actually try to use it, below
try:
    import paho.mqtt.client as mqtt  # import the client | $ pip installing paho-mqtt is necessary
    import paho.mqtt.publish
    PAHO_ENABLED = True
except ModuleNotFoundError:
    PAHO_ENABLED = False

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.formats import Text  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402


class MQTTWriter(Writer):
    """Write to paho-mqtt broker channel."""

    def __init__(self, broker, channel, client_name):
        """
        Write text records to a paho-mqtt broker channel.
        ```
        broker       MQTT broker to connect, broker format[###.###.#.###]
        channel      MQTT channel to read from, channel format[@broker/path_of_subscripton]
        ```
        See /readers/mqtt_reader.py for info on how to start a broker
        """
        super().__init__(input_format=Text)

        if not PAHO_ENABLED:
            raise ModuleNotFoundError('MQTTReader(): paho-mqtt is not installed. Please '
                                      'try "pip install paho-mqtt" prior to use.')

        self.broker = broker
        self.channel = channel
        self.client_name = client_name

        try:
            self.paho = mqtt.Client(client_name)

            self.paho.connect(broker)
            self.paho.subscribe(channel)

            while paho.loop() == 0:
                pass

        except mqtt.WebsocketConnectionError as e:
            logging.error('Unable to connect to broker at %s:%s',
                          self.broker, self.channel)
            raise e

    ############################
    def write(self, record):
        """Write the record to the broker channel."""
        if not record:
            return

        # If we've got a list, hope it's a list of records. Recurse,
        # calling write() on each of the list elements in order.
        if isinstance(record, list):
            for single_record in record:
                self.write(single_record)
            return

        # If record is not a string, try converting to JSON. If we don't know
        # how, throw a hail Mary and force it into str format
        # if not type(record) is str:
        #  if type(record) in [int, float, bool, list, dict]:
        #    record = json.dumps(record)
        #  else:
        #    record = str(record)

        try:
            self.paho.publish(self.channel, record)
        except mqtt.WebsocketConnectionError as e:
            logging.error('Unable to connect to broker at %s:%d',
                          self.broker, self.channel)
            raise e
