#!/usr/bin/env python3
"""Quick hack of a script to generate cruise configuration JSON for
Sikuliaq sensors. Sets up one logger for each instrument, each one
listening for UDP packets on the specified port.


To run, first use this script to generate the config file:

   skq/create_skq_config.py < skq/skq/skq_ports.txt > skq/skq_cruise.json

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

import fileinput

# Set to desired cruise ID
cruise = 'SKQ_SAMPLE'

file_db_config = """  "INST": {
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

file_config = """  "INST": {
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

db_config = """  "INST": {
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

file_db_loggers = []
file_loggers = []
db_loggers = []

for line in fileinput.input():
  (inst, port) = line.strip().split('\t', maxsplit=2)

  # FOLLOWING LINE IS FOR TESTING ONLY (SEE README.md). COMMENT IT OUT
  # TO GENERATE A CONFIGURATION WHERE EACH LOGGER READS FROM ITS
  # PROPER PORT.

  #port = '6224'
  
  logger = file_db_config
  logger = logger.replace('INST', inst)
  logger = logger.replace('PORT', port)
  logger = logger.replace('CRUISE', cruise)
  file_db_loggers.append(logger)

  logger = file_config
  logger = logger.replace('INST', inst)
  logger = logger.replace('PORT', port)
  logger = logger.replace('CRUISE', cruise)
  file_loggers.append(logger)

  logger = db_config
  logger = logger.replace('INST', inst)
  logger = logger.replace('PORT', port)
  logger = logger.replace('CRUISE', cruise)
  db_loggers.append(logger)

skq_config = """{
    "cruise": {
        "id": "%s",
        "start": "2018-04-01",
        "end": "2018-05-01"
    },
    "default_mode": "off",
    "modes": {
      // Nothing's running when off
      "off": {},
      "file": {
      %s
      },
      "db": {
      %s
      },
      "file/db": {
      %s
      }
    }
}
"""

print(skq_config % (cruise,
                    ',\n'.join(file_loggers),
                    ',\n'.join(db_loggers),
                    ',\n'.join(file_db_loggers)))
