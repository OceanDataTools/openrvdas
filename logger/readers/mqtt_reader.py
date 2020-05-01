#!/usr/bin/env python3


import json
import logging
import socket
import sys

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.formats import Text
from logger.readers.reader import Reader

try:
  import paho.mqtt.client as mqtt # import the client | $ pip installing paho-mqtt is necessary
  PAHO_ENABLED = True
except ModuleNotFoundError:
  PAHO_ENABLED = False

################################################################################
class MQTTReader(Reader):
  """
  Read messages from an mqtt broker
  """
  def __init__(self, broker, channel):

    """
    Read text records from the channel subscription.
    ```
    channel     MQTT channel to read from, channel format[@broker/path_of_subscripton]
    ```
    """

    super().__init__(output_format=Text)

    if not PAHO_ENABLED:
      raise ModuleNotFoundError('MQTTReader(): paho-mqtt is not installed. Please '
                                'try "pip install paho-mqtt" prior to use.')
    
    self.broker = broker
    self.channel = channel
    
    try:
      self.paho = mqtt.Client('Instance1')

      self.paho.connect(broker)
      self.paho.subscribe(channel)

    except mqtt.WebsocketConnectionError as e:
      logging.error('Unable to connect to broker at %s:%d',
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

################################################################################
