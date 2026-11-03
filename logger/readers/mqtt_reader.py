#!/usr/bin/env python3

import logging
import random
import string
import time
from queue import Queue

# Don't barf if they don't have redis installed. Only complain if
# they actually try to use it, below
try:
    import paho.mqtt.client as mqtt  # import the client | $ pip installing paho-mqtt is necessary
    PAHO_ENABLED = True

    # Check which paho version is being used, so we know how to call it.
    # importlib.metadata is stdlib; the pkg_resources this used to rely on
    # ships with setuptools, which recent Python versions no longer install
    # into a venv by default. When it was missing, the ModuleNotFoundError
    # landed in the handler below and MQTTReader reported that paho-mqtt
    # wasn't installed, even though it was.
    from importlib.metadata import version as _package_version  # noqa: E402
    PAHO_VERSION = _package_version('paho-mqtt')
    USE_VERSION_FLAG = int(PAHO_VERSION.split('.')[0]) >= 2
except ModuleNotFoundError:
    PAHO_ENABLED = False

from logger.readers.reader import Reader  # noqa: E402


################################################################################
class MQTTReader(Reader):
    """
    Read messages from an mqtt broker
    """

    def __init__(self, broker, channel, client_name=None,
                 port=1883, clean_start=None,
                 qos=0, return_as_bytes=False,
                 reconnect=True, reconnect_delay=1, max_reconnect_delay=60,
                 **kwargs):
        """
        Read text records from the channel subscription.
        ```

        broker       MQTT broker to connect, broker format[###.###.#.#]
        channel      MQTT channel to read from, channel format[@broker/path_of_subscripton]
        client_name  Prefix used for `client_id` when connecting to broker.  The `client_id`
                     must be unique for each broker connection, so a random string will be
                     appended to the provided `client_name`.  If None, a random ID is
                     generated for you.
        port         broker port, typically 1883
        clean_start  Request new session on first connection. Options: True, False,
                       or the default of mqtt.MQTT_CLEAN_START_FIRST_ONLY
        qos          Quality of service: 0 = at most once, 1 = at least once, 2 = exactly once
        return_as_bytes
                     If true, return message in bytes, otherwise convert to str
        reconnect    If True (the default), log a warning and try to reconnect when the
                     connection to the broker drops. If False, a dropped connection is
                     logged and read() returns None, signalling end of input, so the
                     logger stops rather than silently receiving nothing.
        reconnect_delay
                     Seconds to wait before the first reconnection attempt. The delay
                     doubles with each failed attempt, up to max_reconnect_delay.
        max_reconnect_delay
                     Ceiling, in seconds, for the reconnection backoff.
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
        if qos not in [0, 1, 2]:
            raise ValueError('MQTTReader parameter qos must be integer value 0, 1 or 2. '
                             f'Found type "{type(qos).__name__}", value "{qos}".')

        # Let's build it!
        super().__init__(**kwargs)

        def on_connect(client, userdata, flags, rc, properties=None):
            logging.info(f'Connected With Result Code: {rc}')
            self.connected = True
            # Subscribe here rather than once at startup: a broker that has
            # dropped us forgets our subscriptions, so every (re)connection
            # has to ask for them again.
            client.subscribe(self.channel, qos=self.qos)

        def on_disconnect(client, userdata, *args):
            """Note that we lost the broker.

            The callback signature differs between paho versions:
              paho 1.x: (client, userdata, rc[, properties])
              paho 2.x: (client, userdata, disconnect_flags, reason_code, properties)
            In both, the interesting value is why we were disconnected.
            """
            if USE_VERSION_FLAG:
                reason = args[1] if len(args) > 1 else None
            else:
                reason = args[0] if args else None
            self.connected = False
            logging.warning('MQTTReader lost connection to broker %s:%d, channel %s: %s',
                            self.broker, self.port, self.channel, reason)

        def on_message(client, userdata, message):
            self.queue.put(message)

        self.broker = broker
        self.channel = channel
        if client_name:
            # If user supplied `client_name`, append random chars to it to
            # attempt to ensure we have a unique `client_id`.
            rand_id = ''.join(random.choices(string.ascii_lowercase+string.digits, k=6))
            self.client_id = f'{client_name}-{rand_id}'
        else:
            # If None is specified, the underlying mqtt library generates a
            # unique id for you.
            self.client_id = None
        self.port = port
        if clean_start is None:
            clean_start = mqtt.MQTT_CLEAN_START_FIRST_ONLY
        self.clean_start = clean_start
        self.qos = qos
        self.return_as_bytes = return_as_bytes
        self.reconnect = reconnect
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.connected = False
        self.queue = Queue()

        try:
            if USE_VERSION_FLAG:
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, self.client_id)
            else:
                self.client = mqtt.Client(self.client_id)

            self.client.on_connect = on_connect
            self.client.on_disconnect = on_disconnect
            self.client.on_message = on_message

            # Subscription happens in on_connect, so it is re-established on
            # every reconnection rather than only on the first connection.
            if USE_VERSION_FLAG:
                self.client.connect(broker, port)
            else:
                self.client.connect(broker, port, clean_start=clean_start)

        except (mqtt.WebsocketConnectionError, ConnectionRefusedError) as e:
            logging.error(f'Unable to connect to broker at {broker}:{port} {channel}')
            raise e

    ############################
    def _reconnect(self, rc):
        """Try to reconnect to the broker, backing off between attempts.

        Returns True once reconnected. Blocks until it succeeds, so a broker
        that is down for a while stalls the logger rather than killing it.
        """
        delay = self.reconnect_delay
        attempt = 0
        while True:
            attempt += 1
            try:
                self.client.reconnect()
                logging.warning('MQTTReader reconnected to broker %s:%d, channel %s '
                                'after %d attempt(s)',
                                self.broker, self.port, self.channel, attempt)
                return True
            except (OSError, mqtt.WebsocketConnectionError) as e:
                # First failure at warning so it's visible; the rest at info so
                # a long outage doesn't flood the logs.
                log = logging.warning if attempt == 1 else logging.info
                log('MQTTReader reconnect to %s:%d failed (attempt %d): %s. '
                    'Retrying in %g seconds.',
                    self.broker, self.port, attempt, e, delay)
                time.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay)

    ############################
    def read(self):
        while True:
            try:
                rc = self.client.loop()
                while not self.queue.empty():
                    message = self.queue.get()
                    if message is None:
                        continue
                    logging.debug('Got message "%s"', message.payload)
                    if self.return_as_bytes:
                        return message.payload
                    else:
                        return str(message.payload, 'utf-8')

                # client.loop() returns non-zero when the network loop has
                # failed - typically because the broker has gone away. Ignoring
                # it means spinning here forever, silently returning nothing,
                # which is the symptom reported in issue #578.
                if rc != mqtt.MQTT_ERR_SUCCESS:
                    if self.reconnect:
                        self._reconnect(rc)
                    else:
                        logging.warning('MQTTReader connection to broker %s:%d lost '
                                        '(rc %s) and reconnect is disabled; '
                                        'returning EOF.',
                                        self.broker, self.port, rc)
                        return None
            except KeyboardInterrupt:
                self.client.disconnect()
                exit(0)
