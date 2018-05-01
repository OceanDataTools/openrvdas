#!/usr/bin/env python3
"""Quick hack of a script to generate cruise configuration JSON for
Sikuliaq sensors. Sets up one logger for each instrument, each one
listening for UDP packets on the specified port.


To run, first use this script to generate the config file:

   skq/create_skq_config.py < skq/skq_ports.txt > skq/skq_cruise.json

Then either hand the config file to the command line run_loggers.py script:

   logger/utils/run_loggers.py \
       --config skq/skq_cruise.json \
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
import pprint
import sys

from collections import OrderedDict

sys.path.append('.')

from logger.utils.read_json import parse_json

# Following line is for testing only (see README.md). Set
# ALL_USE_SAME_PORT to False to generate a configuration where each
# logger reads from its proper port.

ALL_USE_SAME_PORT = False
PORT = '6224'

# Set to desired cruise ID
cruise = 'SKQ_SAMPLE'

file_db_config = """{
          "name": "INST->file/db",
          "readers": {
            "class": "NetworkReader",
            "kwargs": { "network": ":PORT" }
          },
          "transforms": {
            "class": "RegexFilterTransform",
            "kwargs": { "pattern": "^INST" }
          },
          "writers": [
            {
              "class": "ComposedWriter",
              "kwargs": {
                "transforms": {
                  "class": "ParseNMEATransform",
                  "kwargs": {"time_format": "%Y-%m-%dT%H:%M:%S.%fZ"}
                },
                "writers": { "class": "DatabaseWriter" }
              }
            },
            {
              "class": "ComposedWriter",
              "kwargs": {
                "transforms": {
                  "class": "SliceTransform",
                  "kwargs": {"fields": "1:"}
                },
                "writers": {
                  "class": "LogfileWriter",
                  "kwargs": {
                    "filebase": "/tmp/log/CRUISE/INST/raw/CRUISE_INST",
                    "time_format": "%Y-%m-%dT%H:%M:%S.%fZ"
                  }
                }
              }
            }
          ]
        }"""

file_config = """{
          "name": "INST->file",
          "readers": {
            "class": "NetworkReader",
            "kwargs": { "network": ":PORT" }
          },
          "transforms": {
            "class": "RegexFilterTransform",
            "kwargs": { "pattern": "^INST" }
          },
          "writers": {
            "class": "ComposedWriter",
            "kwargs": {
              "transforms": {
                "class": "SliceTransform",
                "kwargs": {"fields": "1:"}
              },
              "writers": {
                "class": "LogfileWriter",
                "kwargs": {
                  "filebase": "/tmp/log/CRUISE/INST/raw/CRUISE_INST",
                  "time_format": "%Y-%m-%dT%H:%M:%S.%fZ"
                }
              }
            }
          }
        }"""

db_config = """{
          "name": "INST->db",
          "readers": {
            "class": "NetworkReader",
            "kwargs": { "network": ":PORT" }
          },
          "transforms": {
            "class": "RegexFilterTransform",
            "kwargs": { "pattern": "^INST" }
          },
          "writers": {
            "class": "ComposedWriter",
            "kwargs": {
              "transforms": {
                "class": "ParseNMEATransform",
                "kwargs": {"time_format": "%Y-%m-%dT%H:%M:%S.%fZ"}
              },
              "writers": { "class": "DatabaseWriter" }
            }
          }
        }"""

lines = [line.strip() for line in sys.stdin.readlines()]

loggers = {}
modes = {}
configs = {}
  
modes['off'] = {}
modes['file'] = {}
modes['db'] = {}
modes['file/db'] = {}

for line in lines:
  (inst, port) = line.split('\t', maxsplit=2)

  if ALL_USE_SAME_PORT:
    port = PORT
  
  config = file_db_config
  config = config.replace('INST', inst)
  config = config.replace('PORT', port)
  config = config.replace('CRUISE', cruise)
  configs['%s->file/db' % inst] = parse_json(config)

  config = file_config
  config = config.replace('INST', inst)
  config = config.replace('PORT', port)
  config = config.replace('CRUISE', cruise)
  configs['%s->file' % inst] = parse_json(config)

  config = db_config
  config = config.replace('INST', inst)
  config = config.replace('PORT', port)
  config = config.replace('CRUISE', cruise)
  configs['%s->db' % inst] = parse_json(config)

  loggers[inst] = {}
  loggers[inst]['configs'] = [
    'off', '%s->file/db' % inst, '%s->file' % inst, '%s->db' % inst
  ]

  modes['file'][inst] = '%s->file' % inst
  modes['db'][inst] = '%s->db' % inst
  modes['file/db'][inst] = '%s->file/db' % inst
  
#pprint.pprint(loggers, width=40, compact=False)
#pprint.pprint(modes, width=40, compact=False)

skq_cruise = OrderedDict()
skq_cruise['cruise'] = {
  'id': '%s' % cruise,
  'start': '2018-04-01',
  'end': '2018-05-01'
}
skq_cruise['loggers'] = loggers
skq_cruise['modes'] = modes
skq_cruise['default_mode'] = 'off'
skq_cruise['configs'] = configs

#pprint.pprint(loggers, width=40, compact=False)
#pprint.pprint(modes, width=40, compact=False)
#pprint.pprint(skq_cruise, width=40, compact=False)
print(json.dumps(skq_cruise, indent=4))
