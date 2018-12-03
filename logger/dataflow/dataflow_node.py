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

    self.quit_flag = False

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
    while not self.quit_flag:
      # If we're reading from somewhere, see if there's anything to
      # read, and process it if there is.
      if self.subscription_list:
        logging.info('Node %s fetching from queue', self.name)
        record = await self.get_next_record()

        logging.debug('Node %s received "%s" from queue', self.name, record)
        result = await self.processor.process(record)
      else:
        result = await self.processor.read()
        logging.info('Node %s read: %s', self.name, result)
        if result is None:
          self.quit()

      # If we have any output from our processing, send it off to our
      # subscribers.
      if result is not None:
        self.send_result_to_subscribers(result)

    logging.warning('Node "%s" exiting run() loop', self.name)
    if not future.cancelled():
      future.set_result('Node "{}" is done'.format(self.name))

  ############################
  def quit(self):
    self.quit_flag = True
    logging.warning('Node "%s" received quit() request', self.name)
