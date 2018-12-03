#!/usr/bin/env python3
"""Read and run a dataflow configuration.
"""
import argparse
import asyncio
import logging
import sys
import time

sys.path.append('.')

from logger.utils.create_component import create_component
from logger.utils.read_config import read_config

from logger.dataflow.asyncio_queue_node import AsyncioQueueNode as Node

run_logging = logging.getLogger(__name__)
#run_logging.setLevel(logging.DEBUG)

################################################################################
class AsyncWrapper:
  """Helper class for wrapping non-async Readers, Writers and Transforms
  into async versions."""
  def __init__(self, component):
    self.component = component

  async def read(self):
    """Call the component's read() method, but put an itsy bitsy asyncio
    sleep() in to allow it to yield execution and give other nodes a
    chance to run.
    """
    logging.debug('Called read() on %s', str(self.component))
    await asyncio.sleep(0.0001)
    return self.component.read()

  async def process(self, record):
    """Call the component's transform() method if it has one on the
    passed record, otherwise look for and call its write() method.
    """
    logging.debug('Called process() on %s', str(self.component))
    if hasattr(self.component, 'transform'):
      return self.component.transform(record)
    if hasattr(self.component, 'write'):
      return self.component.write(record)      
    else:
      raise ValueError('Component has neither transform() nor write() method')

################################################################################
class DataflowRunner:
  """Parse a dataflow definition, instantiate and begin running the nodes."""
  ############################
  def __init__(self, config, name='no_name'):
    """Create a dataflow from a Python config dict."""
    self.config = config
    self.name = name
    self.nodes = None

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

      # For now, assume components are not async, so after we've
      # created them, wrap it in an async class.
      component = create_component(component_def=node_config, name=node_name)
      processor = AsyncWrapper(component)

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
    loop = asyncio.get_event_loop()
    loop.set_debug(enabled=True)

    self.nodes = self.instantiate_nodes(self.config)

    futures = {}
    for node_name, node in self.nodes.items():
      logging.info('Creating future for %s', node_name)
      futures[node_name] = asyncio.Future(loop=loop)
      asyncio.ensure_future(node.run(futures[node_name]))

    try:
      loop.run_forever()
    except KeyboardInterrupt as e:
      # Grabbed from
      # https://stackoverflow.com/questions/30765606/whats-the-correct-way-to-clean-up-after-an-interrupted-event-loop
      logging.warning('Received keyboard interrupt; attempting shutdown...')

      # Do not show `asyncio.CancelledError` exceptions during shutdown
      # (a lot of these may be generated, skip this if you prefer to see them)
      def shutdown_exception_handler(loop, context):
        if "exception" not in context \
        or not isinstance(context["exception"], asyncio.CancelledError):
            loop.default_exception_handler(context)
      loop.set_exception_handler(shutdown_exception_handler)

      # Handle shutdown gracefully by waiting for all tasks to be cancelled
      tasks = asyncio.gather(*asyncio.Task.all_tasks(loop=loop),
                             loop=loop, return_exceptions=True)
      tasks.add_done_callback(lambda t: loop.stop())
      tasks.cancel()

      # Keep the event loop running until it is either destroyed or all
      # tasks have really terminated
      while not tasks.done() and not loop.is_closed():
        loop.run_forever()

    finally:
      logging.warning('All tasks terminated - exiting.')
      loop.close()
  
################################################################################
if __name__ == '__main__':
  parser = argparse.ArgumentParser()

  ############################
  # Set up from config file
  parser.add_argument('--config', dest='config_file', default=None,
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

  config = read_config(args.config_file) if args.config_file else None

  dataflow_runner = DataflowRunner(config=config)
  dataflow_runner.run()
