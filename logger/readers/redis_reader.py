#!/usr/bin/env python3

import logging
import sys

# Don't barf if they don't have redis installed. Only complain if
# they actually try to use it, below
try:
    import redis
    REDIS_ENABLED = True
except ModuleNotFoundError:
    REDIS_ENABLED = False

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.reader import Reader  # noqa: E402
from logger.utils.formats import Text  # noqa: E402

DEFAULT_HOST = 'localhost'
DEFAULT_PORT = '6379'


################################################################################
class RedisReader(Reader):
    """Read messages from a redis pubsub channel."""

    def __init__(self, channel, password=None):
        """
        Read text records from a Redis pubsub server channel.
        ```
        channel      Redis channel to read from, format channel[@hostname[:port]]
        ```
        """
        super().__init__(output_format=Text)

        if not REDIS_ENABLED:
            raise ModuleNotFoundError('RedisReader(): Redis is not installed. Please '
                                      'try "pip3 install redis" prior to use.')
        self.channel = channel
        self.hostname = DEFAULT_HOST
        self.port = DEFAULT_PORT

        if channel.find('@') > 0:
            (self.channel, self.hostname) = channel.split(sep='@', maxsplit=1)
        if self.hostname.find(':') > 0:
            (self.hostname, self.port) = self.hostname.split(sep=':', maxsplit=1)
        self.port = int(self.port)

        # Connect to the specified server and subscribe to channel
        try:
            self.redis = redis.StrictRedis(host=self.hostname, port=self.port,
                                           password=password, decode_responses=True)
            self.pubsub = self.redis.pubsub()
            self.pubsub.subscribe(self.channel)
        except redis.exceptions.ConnectionError as e:
            logging.error('Unable to connect to server at %s:%d',
                          self.hostname, self.port)
            raise e

    ############################
    def read(self):
        """Read/wait for message from pubsub channel."""

        while True:
            message = next(iter(self.pubsub.listen()))
            logging.debug('Got message "%s"', message)
            if message.get('type', None) == 'message':
                data = message.get('data', None)
                if data:
                    return data

        # Alternatively, we could use
        # while True:
        #  message = self.pubsub.get_message(timeout=10)
        #  if message:
        #    record = message.get('data', None)
        #    if record:
        #      return record
