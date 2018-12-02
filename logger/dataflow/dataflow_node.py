#!/usr/bin/env python3
"""Top-level abstract dataflow node class.
"""
import logging

################################################################################
class AbstractDataflowNode:
  """Parse a dataflow definition, instantiate and begin running the nodes."""
  ############################
  def __init__(self, name, processor, subscription_list=None):
    """Create a dataflow node from a Python config dict."""
    self.name = name

    # What object are we going to be calling read() or process() on?
    self.processor = processor

    # Which other nodes will we be reading from?
    self.subscription_list = subscription_list or []
    if not self.subscription_list:
      logging.debug('Node "%s" is not reading from any other node', name)

    self.quit = False

  ############################
  def subscriptions(self):
    """Return list of names of nodes whose output we want to read."""
    return self.subscription_list

  ############################
  def add_subscriber(self, subscriber):
    raise NotImplementedError('Class %s (subclass of DataFlowNode) is missing '
                              'implementation of add_subscriber() method.'
                              % self.__class__.__name__)

  ############################
  async def get_next_record(self):
    raise NotImplementedError('Class %s (subclass of DataFlowNode) is missing '
                              'implementation of get_next_record() method.'
                              % self.__class__.__name__)

  ############################
  def send_result_to_subscribers(self, result):
    raise NotImplementedError('Class %s (subclass of DataFlowNode) is missing '
                              'implementation of send_result_to_subscribers() '
                              'method.' % self.__class__.__name__)

  ############################
  async def run(self, future):
    """Iteratively read from our input queue if we have one (or call our
    generator method), do what we need to do with it and send the
    result to our subscribers.
    """
    while not self.quit:
      # If we're reading from somewhere, see if there's anything to
      # read, and process it if there is.
      if self.subscription_list:
        logging.debug('Node %s fetching from queue', self.name)
        record = await self.get_next_record()

        logging.info('Node %s received "%s" from queue', self.name, record)
        result = await self.processor.process(record)
      else:
        result = await self.processor.read()
        logging.info('Node %s read: %s', self.name, result)

      # If we have any output from our processing, send it off to our
      # subscribers.
      if result:
        self.send_result_to_subscribers(result)

    logging.warning('Node "%s" exiting run() loop', self.name)
    future.set_result('Node "{}" is done'.format(self.name))

  ############################
  def quit(self):
    self.quit_flag = True
    logging.warning('Node "%s" received quit() request', self.name)

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
  def _class_kwargs_from_config(self, class_def):
    """Parse a class's kwargs from a dict."""
    if not type(class_def) in [list, dict]:
      raise ValueError('class_kwargs_from_config expected dict or list; '
                       'got: "{}"'.format(class_def))

    # If we've got a list, recurse on each element
    if type(class_def) is list:
      return [self._class_kwargs_from_config(c) for c in class_def]

    # Get name and constructor for component we're going to instantiate
    class_name = class_def.get('class', None)
    if class_name is None:
      raise ValueError('missing "class" definition in "{}"'.format(class_def))
    class_const = globals().get(class_name, None)
    if not class_const:
      raise ValueError('No component class "{}" found: "{}"'.format(
        class_name, class_def))

    # Get the keyword args for the component
    kwarg_dict = class_def.get('kwargs', {})
    kwargs = self._kwargs_from_config(kwarg_dict)
    if not kwargs:
      logging.info('No kwargs found for component {}'.format(class_name))

    # Instantiate!
    logging.info('Instantiating {}({})'.format(class_name, kwargs))
    component = class_const(**kwargs)
    return component
