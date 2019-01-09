#!/usr/bin/env python3
"""Quick hack of a script to generate cruise configuration JSON for
Sikuliaq sensors. Sets up one logger for each instrument, each one
listening for UDP packets on the specified port.


To run, first use this script to generate the config file:

   test/sikuliaq/create_skq_config.py \
     < test/sikuliaq/skq_ports.txt \
     > test/sikuliaq/skq_cruise.yaml

Then either hand the config file to the command line logger_manager script:

   server/logger_manager.py \
       --config test/sikuliaq/skq_cruise.yaml \
       --mode file/db -v

   (The above command starts loggers running in the config's "file/db"
   mode, which reads from UDP ports and writes the resulting data to
   logfiles and the database, using the default database, host and
   user name, as specified in database/settings.py. Other modes are
   "off", "file", and "db", which each do pretty much what you'd
   expect.)

or load the script via the Django GUI, as described in the gui/
subdirectory.

"""
import json
import logging
import pprint
import sys
import yaml

from collections import OrderedDict

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

# Set to desired cruise ID
cruise = 'SKQ201822S'
date = '2018-12-06'

configs = OrderedDict()

for line in sys.stdin.readlines():
  line = line.strip()
  logging.warning(line)
  (inst, port) = line.split('\t', maxsplit=2)

  configs[inst] = {
    'network': ':' + port,
    'filebase': 'test/nmea/%s/%s/raw/%s_%s-%s' % (cruise, inst, cruise, inst, date)
  }

print(json.dumps(configs, indent=4))
