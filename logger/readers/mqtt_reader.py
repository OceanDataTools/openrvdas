#!/usr/bin/env python3

import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402
from logger.utils.formats import Text  # noqa: E402

# Don't barf if they don't have redis installed. Only complain if
# they actually try to use it, below
try:
    import paho.mqtt.client as mqtt  # import the client | $ pip installing paho-mqtt is necessary
    PAHO_ENABLED = True
except ModuleNotFoundError:
    PAHO_ENABLED = False


################################################################################
class MQTTReader(Reader):
    """
    Read messages from an mqtt broker
    """

    def __init__(self, broker, channel, client_name):
        """
        Read text records from the channel subscription.
        ```

        broker       MQTT broker to connect, broker format[###.###.#.#]
        channel     MQTT channel to read from, channel format[@broker/path_of_subscripton]
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

        super().__init__(output_format=Text)

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

            while self.paho.loop() == 0:
                pass

        except mqtt.WebsocketConnectionError as e:
            logging.error('Unable to connect to broker at %s:%s',
                          self.broker, self.channel)
            raise e

    ############################
    def read(self):
        while True:
            try:
                self.paho.loop_forever()
                message = next(iter(self.paho.listen()))
                logging.debug('Got message "%s"', message)
                if message.get('type', None) == 'message':
                    data = message.get('data', None)
                    if data:
                        return data
            except KeyboardInterrupt:
                self.paho.disconnect()
                exit(0)
