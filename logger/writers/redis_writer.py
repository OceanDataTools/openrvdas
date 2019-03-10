#!/usr/bin/env python3

import json
import logging
import socket
import sys

# Don't barf if they don't have redis installed. Only complain if
# they actually try to use it, below
try:
  import redis
  REDIS_ENABLED = True
except ImportException:
  REDIS_ENABLED = False

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.formats import Text
from logger.writers.writer import Writer

################################################################################
class RedisWriter(Writer):
  """Write to redis server pubsub channel."""
  def __init__(self, channel, password=None):
    """
    Write text records to a Redis pubsub server channel.

    channel      Redis channel to write to, format channel@hostname:port

    num_retry    Number of times to retry if write fails.
    """
    super().__init__(input_format=Text)

    if not REDIS_ENABLED:
      raise ModuleNotFoundError('RedisReader(): Redis is not installed. Please '
                                'try "pip3 install redis" prior to use.')
    try:
      (self.channel, server) = channel.split(sep='@', maxsplit=1)
    except ValueError as e:
      logging.error('RedisWriter channel "%s" must be in format '
                    'channel@hostname:port', channel)
      raise e
    try:
      (self.hostname, self.port) = server.split(sep=':', maxsplit=1)
      self.port = int(self.port)
    except ValueError as e:
      logging.error('RedisWriter channel "%s" must be in format '
                    'channel@hostname:port', channel)
      raise e

    # Connect to the specified server
    try:
      self.redis = redis.StrictRedis(host=self.hostname, port=self.port,
                                     password=password, decode_responses=True)
      self.redis.ping()
      self.pubsub = self.redis.pubsub()
    except redis.exceptions.ConnectionError as e:
      logging.error('Unable to connect to server at %s', server)
      raise e

  ############################
  def write(self, record):
    """Write the record to the pubsub channel."""

    if not record:
      return

    ## If record is not a string, try converting to JSON. If we don't know
    ## how, throw a hail Mary and force it into str format
    #if not type(record) is str:
    #  if type(record) in [int, float, bool, list, dict]:
    #    record = json.dumps(record)
    #  else:
    #    record = str(record)

    try:
      self.redis.publish(self.channel, record)
    except redis.exceptions.ConnectionError as e:
      logging.error('Unable to connect to server at %s', server)
      raise e
