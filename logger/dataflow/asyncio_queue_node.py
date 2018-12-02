#!/usr/bin/env python3
"""Implementation of AbstractDataflowNode that uses asyncio Queues.
"""
import asyncio
import logging
import sys
import threading

sys.path.append('.')

from logger.dataflow.dataflow_node import AbstractDataflowNode

################################################################################
class AsyncioQueueNode(AbstractDataflowNode):
  """Instantiate a dataflow node using asyncio.Queue() for communicating
  results between nodes.
  """
  ############################
  def __init__(self, name, processor, subscription_list=None):
    """Create a dataflow node."""
    super().__init__(name, processor, subscription_list)

    # The queue from which we will take our input data, if any.
    self.in_queue = asyncio.Queue()
    
    # List of nodes that subscribe to our output. Note that we use a
    # threading.Lock rather than an asyncio.Lock because we expect
    # contention from the different threads of multiple nodes that may
    # be trying to subscribe at the same time.
    self.subscribers = []
    self.subscriber_lock = threading.Lock()
     
  ############################
  def add_subscriber(self, subscriber):
    with self.subscriber_lock:
      self.subscribers.append(subscriber)
      logging.info('Added subscription %s -> %s', self.name, subscriber.name)

  ############################
  async def get_next_record(self):
    return await self.in_queue.get()

  ############################
  def send_result_to_subscribers(self, result):
    for sub in self.subscribers:
      sub.in_queue.put_nowait(result)
     

