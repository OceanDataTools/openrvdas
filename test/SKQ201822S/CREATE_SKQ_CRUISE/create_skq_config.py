#!/usr/bin/env python3
"""Quick hack of a script to generate cruise configuration JSON for
Sikuliaq sensors. Sets up one logger for each instrument, each one
listening for UDP packets on the specified port.

To run, first use this script to generate the config file:

   test/SKQ201822S/CREATE_SKQ_CRUISE/create_skq_config.py \
     < test/SKQ201822S/CREATE_SKQ_CRUISE/skq_ports.txt \
     > test/SKQ201822S/SKQ201822S_cruise.yaml

Then either hand the config file to the command line logger_manager script:

   server/logger_manager.py \
       --config test/SKQ201822S/SKQ201822S_cruise.yaml \
       --mode file \
       --start_data_server

The above command starts loggers running in the config's "file" mode,
which reads from UDP ports and writes the resulting data to
logfiles. Other modes are "off", "file/db", and "db", which each do
pretty much what you'd expect.

The --start_data_server flag tells the logger_manager.py script to start up a CachedDataServer that will listen


NOTE: For the above logger_manager.py command to run successfully, you
will need to either have live data being served on the appropriate
ports or you will need to run the logger/utils/simulate_network.py
script to have it feed stored data to those ports:

  logger/utils/simulate_network.py  \
    --config test/SKQ201822S/network_sim_SKQ201822S.yaml \
    --loop

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
          "name": "%INST%->file/db",
          "readers": {
            "class": "NetworkReader",
            "kwargs": { "network": ":%PORT%" }
          },
          "transforms": {
            "class": "RegexFilterTransform",
            "kwargs": { "pattern": "^%INST%" }
          },
          "writers": [
            {
              "class": "ComposedWriter",
              "kwargs": {
                "transforms": {
                  "class": "ParseNMEATransform",
                  "kwargs": {
                    "sensor_path":
                      "local/sensor/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensors.yaml",
                    "sensor_model_path":
                      "local/sensor_model/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensor_models.yaml",
                    "time_format": "%Y-%m-%dT%H:%M:%S.%fZ"
                  }
                },
                "writers": [
                  { "class": "DatabaseWriter" },
                  { "class": "NetworkWriter",
                    "kwargs": {"network": ":6225" }}
                ]
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
                    "filebase": "/var/tmp/log/%CRUISE%/%INST%/raw/%CRUISE%_%INST%",
                    "time_format": "%Y-%m-%dT%H:%M:%S.%fZ"
                  }
                }
              }
            }
          ]
        }"""

file_config = """{
          "name": "%INST%->file",
          "readers": {
            "class": "NetworkReader",
            "kwargs": { "network": ":%PORT%" }
          },
          "transforms": {
            "class": "RegexFilterTransform",
            "kwargs": { "pattern": "^%INST%" }
          },
          "writers": [
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
                    "filebase": "/var/tmp/log/%CRUISE%/%INST%/raw/%CRUISE%_%INST%",
                    "time_format": "%Y-%m-%dT%H:%M:%S.%fZ"
                  }
                }
              }
            },
            {
              "class": "ComposedWriter",
              "kwargs": {
                "transforms": {
                  "class": "ParseNMEATransform",
                  "kwargs": {
                    "sensor_path":
                      "local/sensor/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensors.yaml",
                    "sensor_model_path":
                      "local/sensor_model/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensor_models.yaml",
                    "time_format": "%Y-%m-%dT%H:%M:%S.%fZ"
                    }
                },
                "writers": {
                  "class": "NetworkWriter",
                  "kwargs": {"network": ":6225" }
                }
              }
            }
          ]
        }"""

db_config = """{
          "name": "%INST%->db",
          "readers": {
            "class": "NetworkReader",
            "kwargs": { "network": ":%PORT%" }
          },
          "transforms": {
            "class": "RegexFilterTransform",
            "kwargs": { "pattern": "^%INST%" }
          },
          "writers": {
            "class": "ComposedWriter",
            "kwargs": {
              "transforms": {
                "class": "ParseNMEATransform",
                "kwargs": {
                  "sensor_path":
                    "local/sensor/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensors.yaml",
                  "sensor_model_path":
                    "local/sensor_model/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensor_models.yaml",
                  "time_format": "%Y-%m-%dT%H:%M:%S.%fZ"
                  }
              },
              "writers": [
                { "class": "DatabaseWriter" },
                { "class": "NetworkWriter",
                  "kwargs": {"network": ":6225" }}
              ]
            }
          }
        }"""

display_on_config =  {
          "name": "display->on",
          "readers": [],
          "transforms": {
            "class": "ParseNMEATransform",
            "kwargs": {
              "sensor_model_path": "local/sensor_model/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensor_models.yaml",
              "sensor_path": "local/sensor/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensors.yaml",
            }
          },
          "writers": {
            "class": "CachedDataWriter",
            "kwargs": {
              "back_seconds": 640,
              "websocket": ":8766"
            }
          }
        }

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
  config = config.replace('%INST%', inst)
  config = config.replace('%PORT%', port)
  config = config.replace('%CRUISE%', cruise)
  configs['%s->file/db' % inst] = yaml.load(config)

  config = file_config
  config = config.replace('%INST%', inst)
  config = config.replace('%PORT%', port)
  config = config.replace('%CRUISE%', cruise)
  configs['%s->file' % inst] = yaml.load(config)

  config = db_config
  config = config.replace('%INST%', inst)
  config = config.replace('%PORT%', port)
  config = config.replace('%CRUISE%', cruise)
  configs['%s->db' % inst] = yaml.load(config)

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
