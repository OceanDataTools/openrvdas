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

# Following line is for testing only (see README.md). Set
# ALL_USE_SAME_PORT to False to generate a configuration where each
# logger reads from its proper port.

ALL_USE_SAME_PORT = False
PORT = '6224'

# Set to desired cruise ID
cruise = 'SKQ201822S'

file_db_config = """{
  "name": "INST->file/db",
      "dataflow": {
          "network_reader": {
              "class": "NetworkReader",
              "kwargs": { "network": ":PORT" }
            },
          "filter_transform": {
              "subscription_list": ["network_reader"],
              "class": "RegexFilterTransform",
              "kwargs": { "pattern": "^INST" }
          },
          "parser_transform": {
              "subscription_list": ["filter_transform"],
              "class": "ParseNMEATransform",
              "kwargs": {
                  "sensor_path":
                      "local/sensor/*.yaml,test/sikuliaq/sensors.yaml",
                  "sensor_model_path":
                      "local/sensor_model/*.yaml,test/sikuliaq/sensor_models.yaml",
              }
          },
          "database_writer": {
              "subscription_list": ["parser_transform"],
              "class": "DatabaseWriter"
          },
          "slice_transform": {
              "subscription_list": ["filter_transform"],
              "class": "SliceTransform",
              "kwargs": {"fields": "1:"}
          },
          "logfile_writer": {
              "subscription_list": ["slice_transform"],
              "class": "LogfileWriter",
              "kwargs": {
                  "filebase": "/var/tmp/log/CRUISE/INST/raw/CRUISE_INST",
              }
          }
      }
  }"""

file_config = """{
  "name": "INST->file",
      "dataflow": {
          "network_reader": {
              "class": "NetworkReader",
              "kwargs": { "network": ":PORT" }
            },
          "filter_transform": {
              "subscription_list": ["network_reader"],
              "class": "RegexFilterTransform",
              "kwargs": { "pattern": "^INST" }
          },
          "parser_transform": {
              "subscription_list": ["filter_transform"],
              "class": "ParseNMEATransform",
              "kwargs": {
                  "sensor_path":
                      "local/sensor/*.yaml,test/sikuliaq/sensors.yaml",
                  "sensor_model_path":
                      "local/sensor_model/*.yaml,test/sikuliaq/sensor_models.yaml",
              }
          },
          "slice_transform": {
              "subscription_list": ["filter_transform"],
              "class": "SliceTransform",
              "kwargs": {"fields": "1:"}
          },
          "logfile_writer": {
              "subscription_list": ["slice_transform"],
              "class": "LogfileWriter",
              "kwargs": {
                  "filebase": "/var/tmp/log/CRUISE/INST/raw/CRUISE_INST",
              }
          }
      }
  }"""

db_config = """{
  "name": "INST->db",
      "dataflow": {
          "network_reader": {
              "class": "NetworkReader",
              "kwargs": { "network": ":PORT" }
            },
          "filter_transform": {
              "subscription_list": ["network_reader"],
              "class": "RegexFilterTransform",
              "kwargs": { "pattern": "^INST" }
          },
          "parser_transform": {
              "subscription_list": ["filter_transform"],
              "class": "ParseNMEATransform",
              "kwargs": {
                  "sensor_path":
                      "local/sensor/*.yaml,test/sikuliaq/sensors.yaml",
                  "sensor_model_path":
                      "local/sensor_model/*.yaml,test/sikuliaq/sensor_models.yaml",
              }
          },
          "database_writer": {
              "subscription_list": ["parser_transform"],
              "class": "DatabaseWriter"
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
  logging.warning(line)
  (inst, port) = line.split('\t', maxsplit=2)

  if ALL_USE_SAME_PORT:
    port = PORT

  configs['%s->off' % inst] = {}

  config = file_db_config
  config = config.replace('INST', inst)
  config = config.replace('PORT', port)
  config = config.replace('CRUISE', cruise)
  #configs['%s->file/db' % inst] = yaml.load(config)

  config = file_config
  config = config.replace('INST', inst)
  config = config.replace('PORT', port)
  config = config.replace('CRUISE', cruise)
  configs['%s->file' % inst] = yaml.load(config)

  config = db_config
  config = config.replace('INST', inst)
  config = config.replace('PORT', port)
  config = config.replace('CRUISE', cruise)
  #configs['%s->db' % inst] = yaml.load(config)

  loggers[inst] = {}
  loggers[inst]['configs'] = [
    '%s->off' % inst, '%s->file/db' % inst, '%s->file' % inst, '%s->db' % inst
  ]

  modes['off'][inst] = '%s->off' % inst
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
