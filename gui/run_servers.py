#!/usr/bin/env python3
""" Run the status server and logger server, repeatedly, until
    we're shut down by a Ctl-C.

Typically invoked via the web interface:

  # Create an expanded configuration
  logger/utils/build_config.py \
     --config test/configs/sample_cruise.json > config.json

  # If this is your first time using the test server, run
  ./manage.py makemigrations manager
  ./manage.py migrate

  # Run the Django test server
  ./manage.py runserver localhost:8000

  # In a separate window, run the script that runs servers:
  gui/run_servers.py

  # Point your browser at http://localhost:8000, log in and load the
  # configuration you created using the "Choose file" and "Load
  # configuration file" buttons at the bottom of the page.

The run_servers.py script examines the state of the Django ServerState
database to determine which servers should be running (on startup, it
sets the desired run state of both StatusServer and LoggerServer to
"run", then loops and monitors whether they are in fact running, and
restarts them if they should be and are not.

The StatusServer and LoggerServer can be run manually from the command
line as well, using the expected invocation:

  gui/status_server.py
  gui/status_server.py

Use the --help flag to see what options are available with each.

********************************************************************* 
Note: To get this to work using the sample config sample_cruise.json
above, sample_cruise.json, you'll also need to run

  logger/utils/serial_sim.py --config test/serial_sim.py

in a separate terminal window to create the virtual serial ports the
sample config references and feed simulated data through them.)

"""


import logging
import multiprocessing
import os
import sys
import time

sys.path.append('.')

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gui.settings')
django.setup()

from gui.models import ServerMessage, ServerState

from gui.status_server import StatusServer
from gui.logger_server import LoggerServer

# Not implemented!
DEFAULT_NUM_TRIES = 3

DEFAULT_SERVERS = {
  'StatusServer': StatusServer,
  'LoggerServer': LoggerServer,
}
DEFAULT_INTERVAL = 0.5

################################################################################
class ServerRunner:
  ############################
  def __init__(self, servers=DEFAULT_SERVERS, init_args=None,
               interval=DEFAULT_INTERVAL):
    self.servers = servers
    self.init_args = init_args
    self.interval = interval
    self.process = {}

  ############################
  def run_server(self, server_name):
    server_process = None
    server_class = self.servers[server_name]
    if self.init_args and server_name in self.init_args:
      init_args = self.init_args[server_name]
    else:
      init_args = ()
      
    try:
      while True:
        # Does process appear to really be running?
        logging.debug('Checking server %s', server_name)
        while server_process and server_process.is_alive():
          time.sleep(self.interval)

        # If here, we appear to no longer be running. Kick it while it's
        # down, then try restarting.
        logging.warning('Restarting %s', server_name)
        if server_process:
          server_process.terminate()

        # Record that, at this moment, we're not running, but we want to be
        ServerState(server=server_name, running=False, desired=True).save()

        server_object = server_class(*init_args)
        server_process = multiprocessing.Process(target=server_object.start)
        server_process.start()

        # Record that, at this moment, we think we're running
        ServerState(server=server_name, running=True, desired=True).save()    
        time.sleep(self.interval)
    except KeyboardInterrupt:
      logging.warning('Received interrupt. Shutting down %s', server_name)
      ServerState(server=server_name, running=False, desired=False).save()
      if server_process:
        server_process.terminate()
    
  ############################
  def start(self):
    try:
      for (server, server_class) in self.servers.items():
        self.process[server] = multiprocessing.Process(
          target=self.run_server, args=(server,))
        self.process[server].start()

      # Wait for processes to terminate (which they never should, right?)
      for server in self.servers:
        self.process[server].join()
    except KeyboardInterrupt:
      self.quit()
    

  ############################
  def quit(self):
    for (server, server_process) in self.process.items():
      server_process.terminate()

################################################################################
if __name__ == '__main__':
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument('--interval', dest='interval', action='store',
                      type=float, default=1,
                      help='How many seconds to sleep between status checks.')
  parser.add_argument('--num_tries', dest='num_tries', action='store', type=int,
                      default=DEFAULT_NUM_TRIES,
                      help='Number of times to retry failed servers.')
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()
  
  # Set up logging levels
  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  LOG_LEVELS = {0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  logging.basicConfig(format=LOGGING_FORMAT)
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  #run_servers(args.interval, args.num_tries)
  server_runner = ServerRunner()
  server_runner.start()
  
