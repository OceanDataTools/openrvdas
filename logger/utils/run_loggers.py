#!/usr/bin/env python3
"""Run loggers. This is just a wrapper around the LoggerRunner object.

== TYPICAL USE

  # Create an expanded configuration
  logger/utils/build_config.py --config test/configs/sample_cruise.json > config.json

  # Run the loggers from the "port" mode of that configuration
  logger/utils/run_loggers.py --config config.json --mode port -v

(To get this to work using the sample config sample_cruise.json above,
sample_cruise.json, you'll also need to run

  logger/utils/serial_sim.py --config test/serial_sim.py

in a separate terminal window to create the virtual serial ports the
sample config references and feed simulated data through them.)

When used with the sample invocation above, you can verify operation
of the script by monitoring port 6224, to which the loggers write when
in "port" and "underway" mode, and writing the output to stdout:

  logger/listener/listen.py --network :6224 --write_file -

== CHANGING MODES

While it is a little messy, the script accepts mode changes via the
command line. If you type in a mode name (such as "port" given the
above config file), the script will load the configurations
corresponding to that mode. Note that your input is liable to be
interspersed with diagnostic output, making it difficult to see the
mode being typed in.

The script also accepts a "quit" command, which shuts down all loggers
and exits.
"""
import argparse
import logging
import sys
import threading

sys.path.append('.')

from logger.utils.read_json import read_json
from logger.utils.logger_runner import LoggerRunner

run_logging = logging.getLogger(__name__)

################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('--config', dest='config', action='store', required=True,
                      help='Name of configuration file to load and expand.')
  parser.add_argument('--mode', dest='mode', action='store', default=None,
                      help='Optional name of mode to start system in.')
  parser.add_argument('--interactive', dest='interactive', action='store_true',
                      help='(Deprecated - script now interactive by default) '
                      'Whether to interactively accept mode changes from '
                      'the command line.')
  parser.add_argument('--interval', dest='interval', action='store',
                      type=int, default=1,
                      help='How many seconds to sleep between logger checks.')
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  parser.add_argument('-V', '--logger_verbosity', dest='logger_verbosity',
                      default=0, action='count',
                      help='Increase output verbosity of component loggers')
  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'

  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}

  # Our verbosity
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  run_logging.setLevel(LOG_LEVELS[args.verbosity])

  # Verbosity of our component loggers (and everything else)
  args.logger_verbosity = min(args.logger_verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.logger_verbosity])

  logger_runner = LoggerRunner(interval=args.interval)
  run_thread = threading.Thread(target=logger_runner.run)
  run_thread.start()

  cruise_config_json = read_json(args.config)
  configs = cruise_config_json.get('modes', None)
  if not configs:
    raise ValueError('Config file "%s" has no "modes" field' % args.config)

  if args.interactive:
    logging.warning('NOTE: "--interactive" flag is deprecated. This script '
                    'is now interactive by default')

  # Did they give us a desired mode on the command line?
  if args.mode:
    mode_config = configs.get(args.mode, None)
    if mode_config is None:
      raise ValueError('Config file "%s" has no mode "%s"' %
                       (args.config, args.mode))
    logger_runner.set_configs(mode_config)    

  # Loop, trying new modes, until we receive a keyboard interrupt
  try:
    while True:
      new_mode = input('mode? ')

      if new_mode == 'quit':
        break
      
      mode_config = configs.get(new_mode, None)
      if mode_config is None:
        logging.error('Config file "%s" has no mode "%s"' %
                      (args.config, new_mode))
        logging.error('Valid modes are %s and quit.', ', '.join(configs.keys()))
      else:
        print('Setting mode to %s' % new_mode)
        logging.info('#### Setting mode to %s', new_mode)
        logger_runner.set_configs(mode_config)

  # On keyboard interrupt, break from our own loop and signal the
  # run() thread that it should clean up and terminate.
  except KeyboardInterrupt:
    pass

  logger_runner.quit()
    
