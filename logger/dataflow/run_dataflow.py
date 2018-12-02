#!/usr/bin/env python3
"""Reads and runs a dataflow configuration.

"""
import argparse
import asyncio
import logging
import re
import sys
import time

sys.path.append('.')

from logger.utils.read_config import read_config
from logger.dataflow.asyncio_queue_node import AsyncioQueueNode as Node

######
# Dummy assignments to test getting started with workflow
class DummyReader:
  def __init__(self, name='no_name_reader'):
    self.name = name
  async def read(self):
    await asyncio.sleep(0.5)
    return 'Dummy record from ' + self.name

class DummyProcessor:
  def __init__(self, name='no_name_transform'):
    self.name = name
  async def process(self, record):
    return self.name + ' Transformed this record: ' + record

class DummyWriter:
  def __init__(self, name='no_name_writer'):
    self.name = name
  async def process(self, record):
    print('{} got output: {}'.format(self.name, record))
    return None

################################################################################
class DataflowRunner:
  """Parse a dataflow definition, instantiate and begin running the nodes."""
  ############################
  def __init__(self, config):
    """Create a dataflow from a Python config dict."""
    self.config = config
    self.nodes = self.instantiate_nodes(config)

  ############################
  def instantiate_nodes(self, config):
    """Create a dict mapping node names to DataflowNode objects.
    """
    # First, create the nodes
    nodes = {}
    for node_name, node_config in config.items():
      # Who, if anyone, will this node be reading from?
      subscription_list = node_config.get('subscription_list', [])
      if not subscription_list:
        logging.warning('Node "%s" is not reading from any other node',
                        node_name)

      # What class is it implementing? With what arguments?
      class_name = node_config.get('class', None)
      if class_name is None:
        raise ValueError('Node definition {} missing "class" '
                         'specification.'.format(name))
      kwargs = node_config.get('kwargs', None)

      if class_name == 'dummy_reader':
        processor = DummyReader(node_name)
      elif class_name == 'dummy_transform':
        processor = DummyProcessor(node_name)
      elif class_name == 'dummy_writer':
        processor = DummyWriter(node_name)
      else:
        raise ValueError('Node "{}" unknown processor: '
                         '"{}"'.format(node_name, class_name))
      # Create the node
      nodes[node_name] = Node(node_name, processor, subscription_list)

    # Now connect each one up to its subscribers
    for node_name, node in nodes.items():
      for source_name in node.subscriptions():
        source = nodes.get(source_name, None)
        if source is None:
          raise ValueError('Node "{}" attempting to subscribe to node "{}", '
                           'but node "{}" does not exist'
                           ''.format(node_name, source_name, source_name))
        source.add_subscriber(node)

    return nodes

  ############################
  def run(self):

    futures = {}
    for node_name, node in self.nodes.items():
      logging.info('Creating future for %s', node_name)
      futures[node_name] = asyncio.Future()
      asyncio.ensure_future(node.run(futures[node_name]))

    loop = asyncio.get_event_loop()
    loop.set_debug(enabled=True)

    logging.info('Getting ready to run forever...')
    try:
      loop.run_forever()
    finally:
      logging.warning('In "finally" section of run')
      loop.close()
  

  ############################
  ############################
  ############################
  ############################
  def _kwargs_from_config(self, config_json):
    """Parse a kwargs from a JSON string, making exceptions for keywords
    'readers', 'transforms', and 'writers' as internal class references."""
    kwargs = {}
    for key, value in config_json.items():

      # Declaration of readers, transforms and writers. Note that the
      # singular "reader" is a special case for TimeoutReader that
      # takes a single reader.
      if key in ['reader', 'readers', 'transforms', 'writers']:
        kwargs[key] = self._class_kwargs_from_config(value)

      # If value is a simple float/int/string/etc, just add to keywords
      elif type(value) in [float, bool, int, str, list]:
        kwargs[key] = value

      # Else what do we have?
      else:
        raise ValueError('unexpected key:value in configuration: '
                         '{}: {}'.format(key, str(value)))
    return kwargs

  ############################
  def _class_kwargs_from_config(self, class_json):
    """Parse a class's kwargs from a JSON string."""
    if not type(class_json) in [list, dict]:
      raise ValueError('class_kwargs_from_config expected dict or list; '
                       'got: "{}"'.format(class_json))

    # If we've got a list, recurse on each element
    if type(class_json) is list:
      return [self._class_kwargs_from_config(c) for c in class_json]

    # Get name and constructor for component we're going to instantiate
    class_name = class_json.get('class', None)
    if class_name is None:
      raise ValueError('missing "class" definition in "{}"'.format(class_json))
    class_const = globals().get(class_name, None)
    if not class_const:
      raise ValueError('No component class "{}" found: "{}"'.format(
        class_name, class_json))

    # Get the keyword args for the component
    kwarg_dict = class_json.get('kwargs', {})
    kwargs = self._kwargs_from_config(kwarg_dict)
    if not kwargs:
      logging.info('No kwargs found for component {}'.format(class_name))

    # Instantiate!
    logging.info('Instantiating {}({})'.format(class_name, kwargs))
    component = class_const(**kwargs)
    return component

################################################################################
if __name__ == '__main__':
  parser = argparse.ArgumentParser()

  ############################
  # Set up from config file
  parser.add_argument('--config', dest='config', default=None,
                      help='YAML-formatted node configuration file to read.')

  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')

  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

  # Set our logging verbosity
  logging.basicConfig(format=LOGGING_FORMAT)
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  #run_logging.setLevel(LOG_LEVELS[args.verbosity])

  config = read_config(args.config) if args.config else None

  dataflow_runner = DataflowRunner(config=config)
  dataflow_runner.run()
