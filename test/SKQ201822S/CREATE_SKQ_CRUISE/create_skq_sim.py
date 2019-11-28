#!/usr/bin/env python3
"""This script creates the script that the
logger/utils/simulate_network.py script uses to set up a network feed
of simulated data for/from cruise SKQ201822S.

To run, first use this script to generate the config file:

   test/SKQ201822S/CREATE_SKQ_CRUISE/create_skq_sim.py \
     < test/SKQ201822S/CREATE_SKQ_CRUISE/skq_ports.txt \
     > test/SKQ201822S/simulate_SKQ201822S.yaml

Then hand the resulting file to logger/utils/simulate_network.py:

  logger/utils/simulate_data.py \
    --config test/SKQ201822S/simulate_SKQ201822S.yaml \
    --loop

This will begin feeding stored data from sensors to the appropriate
UDP port so that it can be read by the logger_manager.py script.

   server/logger_manager.py \
       --config test/SKQ201822S/SKQ201822S_cruise.yaml \
       --mode file -v

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

HEADER_STR = """# Created by create_skq_sim.py via a command like
#
#  test/SKQ201822S/CREATE_SKQ_CRUISE/create_skq_sim.py \\
#      < test/SKQ201822S/CREATE_SKQ_CRUISE/skq_ports.txt
#
# To be run using
#
#  logger/utils/simulate_data.py \\
#      --config test/SKQ201822S/simulate_SKQ201822S.yaml
#"""

print(HEADER_STR)

for line in sys.stdin.readlines():
  line = line.strip()
  (inst, port) = line.split('\t', maxsplit=2)

  config_str = """%s:
  class: UDP
  port: %s
  filebase: test/%s/%s/raw/%s_%s-%s
""" % (inst, port, cruise, inst, cruise, inst, date)
  print(config_str)

