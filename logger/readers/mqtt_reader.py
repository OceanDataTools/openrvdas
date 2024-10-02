#!/usr/bin/env python3

import logging
import sys
from queue import Queue

# Don't barf if they don't have redis installed. Only complain if
# they actually try to use it, below
try:
    import paho.mqtt.client as mqtt  # import the client | $ pip installing paho-mqtt is necessary
    PAHO_ENABLED = True

    # Check which paho version is being used
    from pkg_resources import get_distribution, packaging  # noqa: E402
    PAHO_VERSION = get_distribution('paho-mqtt').version
    if packaging.version.parse(PAHO_VERSION) >= packaging.version.parse('2.0.0'):
        USE_VERSION_FLAG = True
    else:
        USE_VERSION_FLAG = False
except ModuleNotFoundError:
    PAHO_ENABLED = False

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402


################################################################################
class MQTTReader(Reader):
    """
    Read messages from an mqtt broker
    """

    def __init__(self, broker, channel, client_name,
                 port=1883,
                 clean_start=None,
                 qos=0, return_as_bytes=False):
        """
        Read text records from the channel subscription.
        ```

        broker       MQTT broker to connect, broker format[###.###.#.#]
        channel      MQTT channel to read from, channel format[@broker/path_of_subscripton]
        port         broker port, typically 1883
        clean_start  Request new session on first connection. Options: True, False,
                       or the default of mqtt.MQTT_CLEAN_START_FIRST_ONLY
        qos          Quality of service: 0 = at most once, 1 = at least once, 2 = exactly once
        return_as_bytes
                     If true, return message in bytes, otherwise convert to str
        ```
        Instructions on how to start an MQTT broker:

        1. First install the Mosquitto Broker :
            ```
            sudo apt-get update
            sudo apt-get install mosquitto
            sudo apt-get install mosquitto-clients
            ```
        2. The mosquitto service starts automatically when downloaded but use :
            ```
            sudo service mosquitto start
            sudo service mosquitto stop
            ```
            to start and stop the service.

        3. To test the install use:
            ```
            netstat -at
            ```
            and you should see the MQTT broker which is the port 1883

        4. In order to manually subscribe to a client use :
            ```
            mosquitto_sub -t "example/topic"
            ```
            and publish a message by using
            ```
            mosquitto_pub -m "published message" -t "certain/channel"
            ```
        5. Mosquitto uses a configuration file "mosquitto.conf" which you can
           find in /etc/mosquitto 	folder

        ```
        """
        if not PAHO_ENABLED:
            raise ModuleNotFoundError('MQTTReader(): paho-mqtt is not installed. Please '
                                      'try "pip install paho-mqtt" prior to use.')
        if not qos in [0, 1, 2]:
            raise ValueError('MQTTReader parameter qos must be integer value 0, 1 or 2. '
                             f'Found type "{type(qos).__name__}", value "{qos}".')

        def on_connect(client, userdata, flags, rc, properties=None):
            logging.info(f'Connected With Result Code: {rc}')

        def on_message(client, userdata, message):
            self.queue.put(message)

        self.broker = broker
        self.channel = channel
        self.client_name = client_name
        self.port = port
        if clean_start is None:
            clean_start = mqtt.MQTT_CLEAN_START_FIRST_ONLY
        self.clean_start = clean_start
        self.qos = qos
        self.return_as_bytes = return_as_bytes
        self.queue = Queue()

        try:
            if USE_VERSION_FLAG:
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_name)
            else:
                self.client = mqtt.Client(client_name)

            self.client.on_connect = on_connect
            self.client.on_message = on_message

            if USE_VERSION_FLAG:
                self.client.connect(broker, port)
                self.client.subscribe(channel, qos=self.qos)
            else:
                self.client.connect(broker, port, clean_start=clean_start)
                self.client.subscribe(channel, options=SubscribeOptions(qos=qos))

        except (mqtt.WebsocketConnectionError, ConnectionRefusedError) as e:
            logging.error(f'Unable to connect to broker at {broker}:{port} {channel}')
            raise e

    ############################
    def read(self):
        while True:
            try:
                self.client.loop()
                while not self.queue.empty():
                    message = self.queue.get()
                    if message is None:
                        continue
                    logging.debug('Got message "%s"', message.payload)
                    if self.return_as_bytes:
                        return message.payload
                    else:
                        return str(message.payload, 'utf-8')
            except KeyboardInterrupt:
                self.client.disconnect()
                exit(0)
